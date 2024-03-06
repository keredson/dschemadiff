import collections, os, re, shutil, sqlite3, sys, tempfile, time, uuid
import magic
import sqlparse
import darp


Table = collections.namedtuple('Table', 'name,tbl_name,rootpage,sql,columns,akas,unique_constraints')
Column = collections.namedtuple('Column', 'cid,name,type,notnull,dflt_value,pk,col_def,akas')
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
        cmds.append(f'ALTER TABLE "{tbl_name}" RENAME COLUMN "{col_name}" TO __dschemadiff_tmp__')
        cmds += _add_column(tbl_name, col2)
        cast_stmt = f'CAST(__dschemadiff_tmp__ as {col2.type})'
        cmds.append(f'UPDATE "{tbl_name}" SET "{col_name}" = '+ (f'COALESCE({cast_stmt}, {col2.dflt_value})' if col2.dflt_value else cast_stmt))
        cmds.append(f'ALTER TABLE "{tbl_name}" DROP COLUMN __dschemadiff_tmp__')
    
    # add unique constraints
    for constraint_columns in sorted(set(tbl2.unique_constraints.values()) - set(tbl1.unique_constraints.values())):
      constraint_name = 'unique_index_%i' % len(tbl2.unique_constraints)
      constraint_columns_sql = ','.join(['"%s"'%s for s in constraint_columns])
      cmds.append(f'CREATE UNIQUE INDEX {constraint_name} ON {tbl_name}({constraint_columns_sql})')

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
    tbl_stmt, column_defs, tbl_constraints, tbl_options = _parse_create_table(tbl.sql)
    
    # find comments
    comments_by_identifier = collections.defaultdict(list)
    for col in column_defs:
      comments_by_identifier[col.identifier] = col.comments
    
    # find table akas
    for comment in tbl_stmt.comments:
      if match := AKA_RE.search(comment):
        tbl.akas.update([s.strip() for s in match.group(1).split(',')])
        break
    
    col_def_by_column_name = {col_def.identifier:col_def for col_def in column_defs}
      
    for row in db.execute(f'select * from pragma_table_info("{tbl.name}");').fetchall():
      # row: cid,name,type,notnull,dflt_value,pk
      name = row[1]
      col_def = col_def_by_column_name[name]
      akas = set()
      for comment in comments_by_identifier[name]:
        if match := AKA_RE.search(comment):
          akas.update([s.strip() for s in match.group(1).split(',')])
      column = Column(*row, col_def, akas)
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
  col_def = column.col_def
  col_def = re.compile(' primary key', re.IGNORECASE).sub('', col_def)
  col_def = re.compile(' unique', re.IGNORECASE).sub('', col_def)
  cmds.append(f'ALTER TABLE "{tbl_name}" ADD COLUMN {col_def}')
  return cmds


def schema_evolve(existing_db, schema_sql, dry_run:bool=True, skip_dry_run:bool=False, apply:bool=False, assume_yes:bool=False, quiet:bool=False):
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
  
  if dry_run and not skip_dry_run:
    tmp_db = os.path.join(tempfile.mkdtemp(), 'test.db')
    if not assume_yes:
      while True:
        v = input('Apply changes (dry run @ %s)? (y/n) ' % tmp_db)
        if v=='n': sys.exit(1)
        if v=='y': break
    if not quiet:
      print('Starting Test Run:', tmp_db)
    shutil.copyfile(existing_db, tmp_db)
    with sqlite3.connect(tmp_db) as db:
      for change in changes:
        if not quiet:
          print(' ', change+';')
        db.execute(change)
    if not quiet:
      print('Successful dry run!')
    os.remove(tmp_db)

  if apply:
    if not assume_yes:
      while True:
        v = input('Apply changes for real (%s)? (y/n) ' % existing_db)
        if v=='n': sys.exit(1)
        if v=='y': break
    # actual run
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
        

class SQLPart(str):
  def __new__(cls, s):
    o = str.__new__(cls, s)
    o.comments = []
    o.identifier = None
    return o
  

def _parse_create_table(sql):
  sql = sql.lower().strip()
  parts = sql.split('(', 1)
  if len(parts)!=2:
    if ' as ' in parts[0]:
      print('AS not supported, skipping:', parts.split('\n')[0].strip())
      return
    raise RuntimeError(f'not a table definition: {sql}')
  tbl_stmt, rest = parts
  tbl_stmt_parts = tbl_stmt.split('--', 1)
  tbl_stmt = SQLPart(tbl_stmt_parts[0].strip())
  if len(tbl_stmt_parts)==2:
    tbl_stmt.comments.append(tbl_stmt_parts[1].strip())
  parts = rest.rsplit(')',1)
  rest, tbl_options = parts if len(parts)==2 else (rest, '')
  column_defs, tbl_constraints = _parse_table_def(tbl_stmt, rest)
  return tbl_stmt, column_defs, tbl_constraints, tbl_options.strip().rstrip(';').strip()


def _parse_table_def(tbl_stmt, sql):
  column_defs, tbl_constraints = [], []
  for part in _parse_table_def_parts(sql):
    if part.startswith('--'):
      tbl_stmt.comments.append(part[2:].strip())
    elif part.split()[0] in ('constraint','primary','unique','check','foreign'):
      tbl_constraints.append(part)
    else:
      column_defs.append(part)
  return column_defs, tbl_constraints

def _parse_table_def_parts(sql):
  stack = []
  end = 0
  i = -1
  part = None
  parts = []
  inner_comments = []
  identifier = None
  comments = []
  while i < len(sql)-1:
    i += 1
    c = sql[i]
    if c==',' and not stack:
      part = SQLPart(sql[end:i].strip())
      part.comments += inner_comments + comments
      part.identifier = identifier
      identifier = None
      inner_comments = []
      comments = []
      parts.append(part)
      end = i+1
      continue
    if c=='-':
      if stack and stack[-1]=='-':
        comment = sql[i-1:sql.index('\n',i)].strip()
        if len(stack) > 1: inner_comments.append(comment[2:].strip())
        elif identifier: comments.append(comment[2:].strip())
        elif part: part.comments.append(comment[2:].strip())
        else: parts.append(comment)
        stack.pop()
        sql = sql[:i-1] + sql[sql.index('\n',i)+1:]
        continue
      else:
        stack.append(c)
      continue
    if c=='(':
      stack.append(c)
      continue
    if c==')' and stack[-1]=='(':
      stack.pop()
      continue
    if c=='"':
      if stack and stack[-1]=='"':
        stack.pop()
        continue
      else:
        stack.append(c)
        continue
    if c==' ' and not stack and not identifier:
      identifier = sql[end:i].strip().strip('"').strip()
      continue
  part = SQLPart(sql[end:].strip())
  part.identifier = identifier
  part.comments += inner_comments + comments
  parts.append(part)
  return parts      
      
    
  

if __name__=='__main__':
  try:
    darp.prep(schema_evolve).run()
  except KeyboardInterrupt:
    print(' [Aborted]')

