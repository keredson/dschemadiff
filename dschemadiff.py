import collections, os, re, shutil, sqlite3, sys, tempfile, time, uuid
import magic
import sqlparse
import darp


Table = collections.namedtuple('Table', 'name,tbl_name,rootpage,sql,columns,akas,unique_constraints')
Column = collections.namedtuple('Column', 'cid,name,type,notnull,dflt_value,pk,tokens,akas')
View = collections.namedtuple('View', 'name,tbl_name,rootpage,sql')

AKA_RE = re.compile(r'AKA\[([A-Za-z0-9_, ]*)\]', re.IGNORECASE)

def _open(s):
  is_vaild_filename = re.sub(r'[^A-Za-z0-9._/\-]', '', s) and 'create table' not in s.lower()
  if is_vaild_filename:
    file_type = magic.from_file(s)
    if file_type == 'ASCII text':
      db = sqlite3.connect(':memory:')
      with open(s) as f:
        sql = f.read()
        for stmt in sqlparse.split(sql):
          db.execute(stmt)
      db.commit()
      return db
    if file_type.startswith('SQLite'):
      db = sqlite3.connect(s)
      return db
    raise RuntimeError('unknown file type %s' % file_type)
  else:
    db = sqlite3.connect(':memory:')
    for stmt in sqlparse.split(s):
      db.execute(stmt)
    db.commit()
    return db

def diff(fn1, fn2, apply=False):
  db1 = _open(fn1)
  db2 = _open(fn2)

  cmds = []
  
  tbls1 = _get_tables(db1)
  tbls2 = _get_tables(db2)
  views1 = _get_views(db1)
  views2 = _get_views(db2)
  
  # add table
  for tbl_name in sorted(tbls2.keys() - tbls1.keys()):
    possible_prev_names = tbls2[tbl_name].akas & (tbls1.keys() - tbls2.keys())
    if len(possible_prev_names) > 1:
      raise RuntimeError(f'{tbl_name}\'s aka list has more than one possible previous name: {",".join(sorted(possible_prev_names))}')
    elif len(possible_prev_names) == 1:
      old_tbl_name = possible_prev_names.pop()
      cmds.append(f'ALTER TABLE "{old_tbl_name}" RENAME TO "{tbl_name}"')
      tbls1[tbl_name] = tbls1[old_tbl_name]
      del tbls1[old_tbl_name]
    else:
      cmds.append(tbls2[tbl_name].sql)

  # drop view
  for view_name in sorted(views1.keys() - views2.keys()):
    cmds.append(f'DROP VIEW "{view_name}"')
  
  # drop table
  for tbl_name in sorted(tbls1.keys() - tbls2.keys()):
    cmds.append(f'DROP TABLE "{tbl_name}"')
    
  for tbl_name in tbls1.keys() & tbls2.keys():
    tbl1 = tbls1[tbl_name]
    tbl2 = tbls2[tbl_name]
    
    # add columns
    for col_name in sorted(tbl2.columns.keys() - tbl1.columns.keys()):
      possible_prev_names = tbl2.columns[col_name].akas & (tbl1.columns.keys() - tbl2.columns.keys())
      if len(possible_prev_names) > 1:
        raise RuntimeError(f'{tbl_name}.{col_name}\'s aka list has more than one possible previous name: {",".join(sorted(possible_prev_names))}')
      elif len(possible_prev_names) == 1:
        old_col_name = possible_prev_names.pop()
        cmds.append(f'ALTER TABLE "{tbl_name}" RENAME COLUMN "{old_col_name}" TO "{col_name}"')
        del tbl1.columns[old_col_name]
      else:
        cmds += _add_column(tbl_name, tbl2.columns[col_name])

    # drop unique constraints
    for constraint_name, constraint_columns in tbl1.unique_constraints.items():
      if constraint_columns not in set(tbl2.unique_constraints.values()):
        cmds.append(f'DROP INDEX {constraint_name}')
  
    # drop columns
    for col_name in sorted(tbl1.columns.keys() - tbl2.columns.keys()):
      cmds.append(f'ALTER TABLE "{tbl_name}" DROP COLUMN {col_name}')
    
    # change column defs
    for col_name in sorted(tbl1.columns.keys() & tbl2.columns.keys()):
      col1 = tbl1.columns[col_name]
      col2 = tbl2.columns[col_name]
      if col1[1:6] != col2[1:6]:
        cmds.append(f'ALTER TABLE "{tbl_name}" RENAME COLUMN "{col_name}" TO __schema_diff_tmp__')
        cmds += _add_column(tbl_name, col2)
        cast_stmt = f'CAST(__schema_diff_tmp__ as {col2.type})'
        cmds.append(f'UPDATE "{tbl_name}" SET "{col_name}" = '+ (f'COALESCE({cast_stmt}, {col2.dflt_value})' if col2.dflt_value else cast_stmt))
        cmds.append(f'ALTER TABLE "{tbl_name}" DROP COLUMN __schema_diff_tmp__')
    
    # add unique constraints
    for constraint_columns in sorted(set(tbl2.unique_constraints.values()) - set(tbl1.unique_constraints.values())):
      constraint_name = 'unique_index_%i' % len(tbl2.unique_constraints)
      constraint_columns_sql = ','.join(['"%s"'%s for s in constraint_columns])
      cmds.append(f'CREATE UNIQUE INDEX {constraint_name} ON tbl({constraint_columns_sql})')

  # add view
  for view_name in sorted(views2.keys() - views1.keys()):
    cmds.append(views2[view_name].sql)
  
  if apply:
    for cmd in cmds:
      db1.execute(cmd)
    db1.commit()
  
  return cmds

def _get_views(db):
  rows = db.execute("select name,tbl_name,rootpage,sql from sqlite_schema where type='view';").fetchall()
  views = [View(*row) for row in rows]
  return {view.name:view for view in views}

def _get_tables(db):
  rows = db.execute("select name,tbl_name,rootpage,sql from sqlite_schema where type='table';").fetchall()
  tbls = [Table(*row, {}, set(), {}) for row in rows]
  for tbl in tbls:
    create_token = [token for token in sqlparse.parse(tbl.sql)[0].tokens if isinstance(token, sqlparse.sql.Parenthesis)][0]
    
    # find comments
    comments_by_identifier = collections.defaultdict(list)
    idx = 0
    last_identifier = None
    while token := create_token.token_matching(lambda t: isinstance(t,sqlparse.sql.Identifier) or isinstance(t,sqlparse.sql.Comment), idx):
      if isinstance(token,sqlparse.sql.Identifier):
        last_identifier = token.value
      if isinstance(token,sqlparse.sql.Comment):
        comments_by_identifier[last_identifier].append(token)
      idx = create_token.token_index(token) + 1
    
    # find table akas
    for comment in comments_by_identifier[None]:
      if match := AKA_RE.search(comment.value):
        tbl.akas.update([s.strip() for s in match.group(1).split(',')])
        break
      
    tokens_by_column_name = {}
    idx = 0
    while idx < len(create_token.tokens):
      next_idx = create_token.token_next_by(idx=idx, m=(sqlparse.tokens.Punctuation, ','))[0] or len(create_token.tokens)
      tokens_for_col = create_token.tokens[idx:next_idx]
      while tokens_for_col and (repr(tokens_for_col[0]).startswith('<Punctuation') or repr(tokens_for_col[0]).startswith('<Whitespace') or repr(tokens_for_col[0]).startswith('<Newline') or repr(tokens_for_col[0]).startswith('<Comment')):
        tokens_for_col = tokens_for_col[1:]
      while tokens_for_col and (repr(tokens_for_col[-1]).startswith('<Punctuation') or repr(tokens_for_col[-1]).startswith('<Whitespace') or repr(tokens_for_col[-1]).startswith('<Newline') or repr(tokens_for_col[-1]).startswith('<Comment')):
        tokens_for_col = tokens_for_col[:-1]
      column_name = tokens_for_col[0].get_real_name() if tokens_for_col and isinstance(tokens_for_col[0],sqlparse.sql.Identifier) else None
      tokens_by_column_name[column_name] = tokens_for_col
      idx = next_idx
      
    for row in db.execute(f'select * from pragma_table_info("{tbl.name}");').fetchall():
      # row: cid,name,type,notnull,dflt_value,pk
      name = row[1]
      tokens = tokens_by_column_name[name]
      akas = set()
      for comment in comments_by_identifier[name]:
        if match := AKA_RE.search(comment.value):
          akas.update([s.strip() for s in match.group(1).split(',')])
      column = Column(*row, tokens, akas)
      tbl.columns[column.name] = column

    for row in db.execute(f'select name from pragma_index_list("{tbl.name}") where "unique";').fetchall():
      constraint_name = row[0]
      constraint_columns = tuple(sorted([row[0] for row in db.execute(f'select name from pragma_index_info("{constraint_name}")').fetchall()]))
      tbl.unique_constraints[constraint_name] = constraint_columns

  return {tbl.name:tbl for tbl in tbls}
  
def _add_column(tbl_name, column):
  cmds = []
  if column.notnull and not column.dflt_value:
    cmds.append('-- WARNING: adding a not null column without a default value will fail if there is any data in the table')
  col_def = ''.join([token.value for token in column.tokens])
  col_def = re.compile(' primary key', re.IGNORECASE).sub('', col_def)
  cmds.append(f'ALTER TABLE "{tbl_name}" ADD COLUMN {col_def}')
  return cmds


def schema_diff(existing_db, schema_sql, dry_run:bool=False, skip_test_run:bool=False, confirm:bool=True, quiet:bool=False):
  '''Schema Diff Tool'''
  if not quiet:
    print('Existing Database:', existing_db, '(to modify)')
    print('Target Schema:', schema_sql)
  changes = diff(existing_db, schema_sql)
  if not changes:
    if not quiet: print('No changes.')
    return
  if not quiet:
    print('Calculated Changes:')
    for change in changes:
      print(' ', change+';')
  while True:
    v = input('Apply changes? (y/n) ')
    if v=='n': sys.exit(1)
    if v=='y': break
  
  if not skip_test_run:
    tmp_db = os.path.join(tempfile.mkdtemp(), 'test.db')
    if not quiet:
      print('Starting Test Run:', tmp_db)
    shutil.copyfile(existing_db, tmp_db)
    with sqlite3.connect(tmp_db) as db:
      for change in changes:
        if not quiet:
          print(' ', change+';')
        db.execute(change)
    if not quiet:
      print('Success!')
      print('Starting Actual Run:', existing_db)
      print('  in:', end=' ', flush=True)
      for i in range(5,0,-1):
        print(i, end='... ', flush=True)
        time.sleep(1)
      print()
    with sqlite3.connect(existing_db) as db:
      for change in changes:
        if not quiet:
          print(' ', change+';')
        db.execute(change)
    if not quiet:
      print('Success!')
        

if __name__=='__main__':
  try:
    darp.prep(schema_diff).run()
  except KeyboardInterrupt:
    print(' [Aborted]')

