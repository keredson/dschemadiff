import pytest, sqlite3
from schema_evolve import diff, _parse_create_table


def test_add_table():
  assert diff(
    'create table tbl1 (a text)',
    '''
      create table tbl1 (a text);
      create table tbl2 (b text);
    ''',
    apply=True
  ) == [
    'CREATE TABLE tbl2 (b text)'
  ]

def test_drop_table():
  assert diff(
    '''
      create table tbl1 (a text);
      create table tbl2 (b text);
    ''',
    'create table tbl1 (a text)',
    apply=True
  ) == [
    'DROP TABLE "tbl2"'
  ]

def test_rename_table():
  assert diff(
    'create table tbl1 (a text)',
    '''
      create table tbl2 (
        -- AKA[tbl1]
        a text
      );
    ''',
    apply=True
  ) == [
    'ALTER TABLE "tbl1" RENAME TO "tbl2"'
  ]

def test_rename_table2():
  assert diff(
    'create table tbl1 (a text)',
    '''
      create table tbl2 ( -- AKA[tbl1]
        a text
      );
    ''',
    apply=True
  ) == [
    'ALTER TABLE "tbl1" RENAME TO "tbl2"'
  ]

def test_add_column():
  assert diff(
    'create table tbl (a text)',
    'create table tbl (a text, b text)',
    apply=True
  ) == [
    'ALTER TABLE "tbl" ADD COLUMN b text'
  ]

def test_add_column_to_table_with_pk():
  # because of https://github.com/andialbrecht/sqlparse/issues/740
  assert diff(
    'create table tbl (a text primary key)',
    'create table tbl (a text primary key, b text)',
    apply=True
  ) == [
    'ALTER TABLE "tbl" ADD COLUMN b text'
  ]

def test_add_column_to_multiple_uniques():
  # because of https://github.com/andialbrecht/sqlparse/issues/740
  assert diff(
    'create table tbl (a text unique)',
    'create table tbl (a text unique, b text unique)',
    apply=True
  ) == [
    'ALTER TABLE "tbl" ADD COLUMN b text',
    'CREATE UNIQUE INDEX unique_index_2 ON tbl("b")'
  ]

def test_add_pk():
  assert diff(
    'create table tbl (a text)',
    'create table tbl (a text, b int PRIMARY KEY)',
    apply=True
  ) == [
    'ALTER TABLE "tbl" ADD COLUMN b int',
    'CREATE UNIQUE INDEX unique_index_1 ON tbl("b")'
  ]

def test_add_column_to_renamed_table():
  assert diff(
    'create table x (a text)',
    '''create table y (
      -- aka[x]
      a text, b text
    )''',
    apply=True
  ) == [
    'ALTER TABLE "x" RENAME TO "y"',
    'ALTER TABLE "y" ADD COLUMN b text'
  ]

def test_delete_column_from_renamed_table():
  assert diff(
    'create table x (a text, b text)',
    '''create table y (
      -- aka[x]
      a text
    )''',
    apply=True
  ) == [
    'ALTER TABLE "x" RENAME TO "y"',
    'ALTER TABLE "y" DROP COLUMN b'
  ]

def test_drop_column():
  assert diff(
    'create table tbl (a text, b text)',
    'create table tbl (a text)',
    apply=True
  ) == [
    'ALTER TABLE "tbl" DROP COLUMN b'
  ]

def test_rename_column():
  assert diff(
    'create table tbl (a text)',
    '''
      create table tbl (
        b text -- AKA[a]
      )
    ''',
    apply=True
  ) == [
    'ALTER TABLE "tbl" RENAME COLUMN "a" TO "b"'
  ]

def test_rename_two_columns():
  assert diff(
    'create table tbl (a text, b text)',
    '''
      create table tbl ( -- AkA[g]
        x text, -- AKA[a]
        y text -- aka[b]
      )
    ''',
    apply=True
  ) == [
    'ALTER TABLE "tbl" RENAME COLUMN "a" TO "x"',
    'ALTER TABLE "tbl" RENAME COLUMN "b" TO "y"'
  ]

def test_rename_table_and_column():
  assert diff(
    'create table x (a text)',
    '''
      create table y ( -- AKA[x]
        b text -- AKA[a]
      )
    ''',
    apply=True
  ) == [
    'ALTER TABLE "x" RENAME TO "y"',
    'ALTER TABLE "y" RENAME COLUMN "a" TO "b"'
  ]

def test_rename_weird_spacing():
  assert diff(
    'create table tbl (a text)',
    '''
      create table tbl (
        b text -- AKA[ a , b, c]
      )
    ''',
    apply=True
  ) == [
    'ALTER TABLE "tbl" RENAME COLUMN "a" TO "b"'
  ]

def test_ambiguous_rename_column():
  with pytest.raises(RuntimeError, match="tbl.c's aka list has more than one possible previous name: a,b"):
    diff(
      'create table tbl (a text, b text)',
      '''
        create table tbl (
          c text -- AKA[a,b]
        )
      '''
    )

def test_ambiguous_rename_table():
  with pytest.raises(RuntimeError, match="z's aka list has more than one possible previous name: x,y"):
    diff(
      '''
        create table x (a text);
        create table y (a text);
      ''',
      '''
        create table z (
          -- aka[x,y]
          a text
        )
      '''
    )

def test_change_column_def():
  assert diff(
    '''
      create table tbl (a int);
      insert into tbl values (1);
    ''',
    'create table tbl (a text)',
    apply=True
  ) == [
    'ALTER TABLE "tbl" RENAME COLUMN "a" TO __dschemadiff_tmp__',
    'ALTER TABLE "tbl" ADD COLUMN a text',
    'UPDATE "tbl" SET "a" = CAST(__dschemadiff_tmp__ as TEXT)',
    'ALTER TABLE "tbl" DROP COLUMN __dschemadiff_tmp__'
  ]

def test_add_not_null():
  assert diff(
    '''
      create table tbl (a text, b text);
    ''',
    'create table tbl (a text, b text not null)',
    apply=True
  ) == [
    'ALTER TABLE "tbl" RENAME COLUMN "b" TO __dschemadiff_tmp__',
    '-- WARNING: adding a not null column without a default value will fail if there is any data in the table',
    'ALTER TABLE "tbl" ADD COLUMN b text not null',
    'UPDATE "tbl" SET "b" = CAST(__dschemadiff_tmp__ as TEXT)',
    'ALTER TABLE "tbl" DROP COLUMN __dschemadiff_tmp__'
  ]

def test_add_not_null_with_default():
  assert diff(
    '''
      create table tbl (a text, b text);
      insert into tbl values ('a', null);
    ''',
    'create table tbl (a text, b text default "woot" not null)',
    apply=True
  ) == [
    'ALTER TABLE "tbl" RENAME COLUMN "b" TO __dschemadiff_tmp__',
    'ALTER TABLE "tbl" ADD COLUMN b text default "woot" not null',
    'UPDATE "tbl" SET "b" = COALESCE(CAST(__dschemadiff_tmp__ as TEXT), "woot")',
    'ALTER TABLE "tbl" DROP COLUMN __dschemadiff_tmp__'
  ]

def test_add_view():
  assert diff(
    'create table tbl (a text);',
    '''
      create table tbl (a text);
      create view v as select * from tbl;
    ''',
    apply=True
  ) == [
    'CREATE VIEW v as select * from tbl'
  ]

def test_drop_view():
  assert diff(
    '''
      create table tbl (a text);
      create view v as select * from tbl;
    ''',
    'create table tbl (a text);',
    apply=True
  ) == [
    'DROP VIEW "v"'
  ]

def test_drop_table_with_view():
  assert diff(
    '''
      create table x (a text);
      create table y (b text);
      create view v as select * from y;
    ''',
    'create table x (a text);',
    apply=True
  ) == [
    'DROP VIEW "v"',
    'DROP TABLE "y"'
  ]

def test_add_unique():
  assert diff(
    'create table tbl (a text)',
    'create table tbl (a text unique)',
    apply=True
  ) == [
    'CREATE UNIQUE INDEX unique_index_1 ON tbl("a")'
  ]

def test_add_multi_column_unique():
  assert diff(
    'create table tbl (a text, b text)',
    'create table tbl (a text, b text, unique(a,b))',
    apply=True
  ) == [
    'CREATE UNIQUE INDEX unique_index_1 ON tbl("a","b")'
  ]

def test_add_column_and_multi_column_unique():
  assert diff(
    'create table tbl (a text)',
    'create table tbl (a text, b text, unique(a,b))',
    apply=True
  ) == [
    'ALTER TABLE "tbl" ADD COLUMN b text',
    'CREATE UNIQUE INDEX unique_index_1 ON tbl("a","b")'
  ]

def test_drop_unique_no_apply():
  assert diff(
    'create table tbl (a text unique)',
    'create table tbl (a text)',
    apply=False
  ) == [
    'DROP INDEX sqlite_autoindex_tbl_1'
  ]

def test_drop_unique():
  with pytest.raises(sqlite3.OperationalError, match="index associated with UNIQUE or PRIMARY KEY constraint cannot be dropped"):
    assert diff(
      'create table tbl (a text unique)',
      'create table tbl (a text)',
      apply=True
    ) == [
      'DROP INDEX sqlite_autoindex_tbl_1'
    ]

def test_parse_create_table():
  tbl_stmt, column_defs, tbl_constraints, tbl_options = _parse_create_table('''
    create table tbl_name (
      id text primary key,
      some_other_id text,
      amount real,
      "final" bool default(false),
      now text default(datetime()),
      foreign key(some_other_id) references some_other_tbl(id)
    ) STRICT;
  ''')
  assert tbl_stmt == 'create table tbl_name'
  assert column_defs == [
    'id text primary key', 
    'some_other_id text', 
    'amount real', 
    '"final" bool default(false)', 
    'now text default(datetime())'
  ]
  assert [cd.identifier for cd in column_defs] == ['id','some_other_id','amount','final','now']
  assert tbl_constraints == ['foreign key(some_other_id) references some_other_tbl(id)']
  assert tbl_options == 'strict'

def test_parse_create_table_with_comment():
  tbl_stmt, column_defs, tbl_constraints, tbl_options = _parse_create_table('''
    create table tbl_name (
      id text primary key,
      amount real, -- aka[ammount] (misspelled)
      something_else bool
    )
  ''')
  assert tbl_stmt == 'create table tbl_name'
  assert column_defs == [
    'id text primary key', 
    'amount real', 
    'something_else bool', 
  ]
  assert [cd.identifier for cd in column_defs] == ['id','amount','something_else']
  assert column_defs[1].comments == ['aka[ammount] (misspelled)']
  assert tbl_constraints == []
  assert tbl_options == ''

def test_parse_create_table_with_comments():
  tbl_stmt, column_defs, tbl_constraints, tbl_options = _parse_create_table('''
    create table tbl_name (
      id text primary key,
      amount real, -- aka[ammount]
      something_else bool -- aka[old_something_else]
    )
  ''')
  assert tbl_stmt == 'create table tbl_name'
  assert column_defs == [
    'id text primary key', 
    'amount real', 
    'something_else bool', 
  ]
  assert [cd.identifier for cd in column_defs] == ['id','amount','something_else']
  assert [cd.comments for cd in column_defs] == [[],['aka[ammount]'],['aka[old_something_else]']]
  assert tbl_constraints == []
  assert tbl_options == ''

def test_parse_create_table_with_table_comment():
  tbl_stmt, column_defs, tbl_constraints, tbl_options = _parse_create_table('''
    create table tbl_name ( -- aka[tbbl_name]
      id text primary key
    )
  ''')
  assert tbl_stmt == 'create table tbl_name'
  assert tbl_stmt.comments == ['aka[tbbl_name]']
  assert column_defs == ['id text primary key']
  assert tbl_constraints == []
  assert tbl_options == ''

def test_parse_create_table_with_table_comment2():
  tbl_stmt, column_defs, tbl_constraints, tbl_options = _parse_create_table('''
    create table tbl_name -- aka[tbbl_name]
    (
      id text primary key
    )
  ''')
  assert tbl_stmt == 'create table tbl_name'
  assert tbl_stmt.comments == ['aka[tbbl_name]']
  assert column_defs == ['id text primary key']
  assert tbl_constraints == []
  assert tbl_options == ''

def test_parse_create_table_with_inner_comment():
  tbl_stmt, column_defs, tbl_constraints, tbl_options = _parse_create_table('''
    create table tbl_name (
      id text primary key,
      amount real(
        -- aka[ammount] (misspelled)
      ),
      something_else bool
    )
  ''')
  assert tbl_stmt == 'create table tbl_name'
  assert column_defs == [
    'id text primary key', 
    'amount real(\n              )', 
    'something_else bool', 
  ]
  assert column_defs[1].comments == ['aka[ammount] (misspelled)']
  assert tbl_constraints == []
  assert tbl_options == ''

def test_add_table2():
  assert diff(
    '',
    '''
      create table tbl (
        id text primary key,
        other_id text,
        amount real,
        final bool default(false),
        now text default(datetime()),
        foreign key(other_id) references other(id)
      );
    ''',
    apply=True
  ) == [
    '''CREATE TABLE tbl (
        id text primary key,
        other_id text,
        amount real,
        final bool default(false),
        now text default(datetime()),
        foreign key(other_id) references other(id)
      )'''
  ]

def test_json_column():
  assert diff(
    'create table tbl (a json)',
    'create table tbl (a json)',
    apply=True
  ) == []

def test_change_text_to_json():
  assert diff(
    'create table tbl (a text)',
    'create table tbl (a json)',
    apply=True
  ) == [
    'ALTER TABLE "tbl" RENAME COLUMN "a" TO __dschemadiff_tmp__',
    'ALTER TABLE "tbl" ADD COLUMN a json',
    'UPDATE "tbl" SET "a" = CAST(__dschemadiff_tmp__ as json)',
    'ALTER TABLE "tbl" DROP COLUMN __dschemadiff_tmp__',
  ]

def test_add_fk_table():
  assert diff(
    '''
      create table a (
        id int primary key
      );
    ''',
    '''
      create table a (
        id int primary key
      );
      create table b (
        id int primary key,
        a_id int,
        foreign key(a_id) references a(id)
      );
    ''',
    apply=True
  ) == [
    '''CREATE TABLE b (
        id int primary key,
        a_id int,
        foreign key(a_id) references a(id)
      )'''
  ]

def test_add_fk_column():
  assert diff(
    '''
      create table a (
        id int primary key
      );
      create table b (
        id int primary key
      );
    ''',
    '''
      create table a (
        id int primary key
      );
      create table b (
        id int primary key,
        a_id int references a(id)
      );
    ''',
    apply=True
  ) == [
    'ALTER TABLE "b" ADD COLUMN a_id int references a(id)'
  ]

def test_change_column_to_fk_column():
  assert diff(
    '''
      create table a (
        id int primary key
      );
      create table b (
        id int primary key,
        a_id int
      );
    ''',
    '''
      create table a (
        id int primary key
      );
      create table b (
        id int primary key,
        a_id int references a(id)
      );
    ''',
    apply=True
  ) == ["-- NOT IMPLEMENTED: add ForeignKey(from_tbl='b', from_cols=('a_id',), to_tbl='a', to_cols=('id',), on_update='NO ACTION', on_delete='NO ACTION', match='NONE')"]

def test_add_fk_constraint():
  assert diff(
    '''
      create table a (
        id int primary key
      );
      create table b (
        id int primary key,
        a_id int
      );
    ''',
    '''
      create table a (
        id int primary key
      );
      create table b (
        id int primary key,
        a_id int,
        foreign key(a_id) references a(id)
      );
    ''',
    apply=True
  ) == ["-- NOT IMPLEMENTED: add ForeignKey(from_tbl='b', from_cols=('a_id',), to_tbl='a', to_cols=('id',), on_update='NO ACTION', on_delete='NO ACTION', match='NONE')"]

def test_drop_fk_constraint():
  assert diff(
    '''
      create table a (
        id int primary key
      );
      create table b (
        id int primary key,
        a_id int,
        foreign key(a_id) references a(id)
      );
    ''',
    '''
      create table a (
        id int primary key
      );
      create table b (
        id int primary key,
        a_id int
      );
    ''',
    apply=True
  ) == ["-- NOT IMPLEMENTED: drop ForeignKey(from_tbl='b', from_cols=('a_id',), to_tbl='a', to_cols=('id',), on_update='NO ACTION', on_delete='NO ACTION', match='NONE')"]



def test_read_files():
  assert diff(
    'data/schema1.sql',
    'data/schema1.db',
    apply=True
  ) == []


