import pytest, sqlite3
from dschemadiff import diff


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






def test_read_files():
  assert diff(
    'data/schema1.sql',
    'data/schema1.db',
    apply=True
  ) == []


