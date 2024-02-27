schema_diff
===========

This is a schema diff tool.  It will calculate the schema changes between two databases or `.sql` files, and optionally apply them.

Why?
----

I mean, Sqlite3 has `sqldiff --schema` right?  Well, given...


```
$ sqlite3 schema1.db "select sql from sqlite_schema"
CREATE TABLE tbl (
  a text
)
$ sqlite3 schema2.db "select sql from sqlite_schema"
CREATE TABLE tbl (
  a text
, b text
)
```

This works: 👏

```
$ sqldiff --schema schema1.db schema2.db 
ALTER TABLE tbl ADD COLUMN b;
```

But this is why I have trust issues... 🤯🤬

```
$ sqldiff --schema schema2.db schema1.db 
DROP TABLE tbl; -- due to schema mismatch
CREATE TABLE tbl (
  a text
);
```

Usage
-----
```
$ python -m schema_diff data/schema1.db data/schema2.sql 
Existing Database: data/schema1.db (to modify)
Target Schema: data/schema2.sql
Calculated Changes:
  ALTER TABLE "tbl" ADD COLUMN b text;
Apply changes? (y/n) y
Starting Test Run: /tmp/tmpdr5vopek/test.db
  ALTER TABLE "tbl" ADD COLUMN b text;
Success!
Starting Actual Run: data/schema1.db
  in: 5... 4... 3... 2... 1... 
  ALTER TABLE "tbl" ADD COLUMN b text;
Success!
```

```
$ python schema_diff.py 
Schema Diff Tool
schema_diff() missing 2 required positional arguments: 'existing_db' and 'schema_sql'
usage: python schema_diff.py <existing_db> <schema_sql> [--dry_run <bool>] [--skip_test_run <bool>] [--confirm <bool>] [--quiet <bool>]
```


Testing
-------
```
$ pytest test.py -vv
============================================ test session starts ============================================
platform linux -- Python 3.11.6, pytest-7.4.0, pluggy-1.2.0 -- /usr/bin/python3
cachedir: .pytest_cache
collected 27 items                                                                                          

test.py::test_add_table PASSED                                                                        [  3%]
test.py::test_drop_table PASSED                                                                       [  7%]
test.py::test_rename_table PASSED                                                                     [ 11%]
test.py::test_rename_table2 PASSED                                                                    [ 14%]
test.py::test_add_column PASSED                                                                       [ 18%]
test.py::test_add_pk PASSED                                                                           [ 22%]
test.py::test_add_column_to_renamed_table PASSED                                                      [ 25%]
test.py::test_delete_column_from_renamed_table PASSED                                                 [ 29%]
test.py::test_drop_column PASSED                                                                      [ 33%]
test.py::test_rename_column PASSED                                                                    [ 37%]
test.py::test_rename_two_columns PASSED                                                               [ 40%]
test.py::test_rename_table_and_column PASSED                                                          [ 44%]
test.py::test_rename_weird_spacing PASSED                                                             [ 48%]
test.py::test_ambiguous_rename_column PASSED                                                          [ 51%]
test.py::test_ambiguous_rename_table PASSED                                                           [ 55%]
test.py::test_change_column_def PASSED                                                                [ 59%]
test.py::test_add_not_null PASSED                                                                     [ 62%]
test.py::test_add_not_null_with_default PASSED                                                        [ 66%]
test.py::test_add_view PASSED                                                                         [ 70%]
test.py::test_drop_view PASSED                                                                        [ 74%]
test.py::test_drop_table_with_view PASSED                                                             [ 77%]
test.py::test_add_unique PASSED                                                                       [ 81%]
test.py::test_add_multi_column_unique PASSED                                                          [ 85%]
test.py::test_add_column_and_multi_column_unique PASSED                                               [ 88%]
test.py::test_drop_unique_no_apply PASSED                                                             [ 92%]
test.py::test_drop_unique PASSED                                                                      [ 96%]
test.py::test_read_files PASSED                                                                       [100%]

============================================ 27 passed in 0.08s =============================================
```



