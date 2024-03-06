Schema Evolve
=============

This is a schema evolution tool (currently only for sqlite).  It will diff schema changes between two databases or `.sql` files, and optionally apply them.

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

Install
-------
```
$ pip install schema-evolve
```

Usage
-----
```
$ python -m schema_evolve data/schema1.db data/schema2.sql --apply
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
$ python schema_evolve.py 
Schema Diff Tool
schema_evolve() missing 2 required positional arguments: 'existing_db' and 'schema_sql'
usage: python schema_evolve.py <existing_db> <schema_sql> [--dry_run] [--skip_dry_run] [--assume-yes] [--quiet]
```

Renaming
--------

To rename a column, add a special comment on the same line specifying the old name.  Example:

```
CREATE TABLE users (
  id INT PRIMARY KEY,
  ip_address TEXT, -- AKA[ip]
)
```

This would rename the column `ip` to `ip_address`.

For tables:

```
CREATE TABLE clients ( -- AKA[users]
  id INT PRIMARY KEY,
  name TEXT
)
```

This would rename the `users` table to `clients`.


Testing
-------
```
$$ pytest test.py -vv
============================================ test session starts ============================================
platform linux -- Python 3.11.6, pytest-7.4.0, pluggy-1.2.0 -- /usr/bin/python3
cachedir: .pytest_cache
rootdir: /home/derek/projects/schema_diff
plugins: requests-mock-1.9.3
collected 38 items                                                                                          

test.py::test_add_table PASSED                                                                        [  2%]
test.py::test_drop_table PASSED                                                                       [  5%]
test.py::test_rename_table PASSED                                                                     [  7%]
test.py::test_rename_table2 PASSED                                                                    [ 10%]
test.py::test_add_column PASSED                                                                       [ 13%]
test.py::test_add_column_to_table_with_pk PASSED                                                      [ 15%]
test.py::test_add_column_to_multiple_uniques PASSED                                                   [ 18%]
test.py::test_add_pk PASSED                                                                           [ 21%]
test.py::test_add_column_to_renamed_table PASSED                                                      [ 23%]
test.py::test_delete_column_from_renamed_table PASSED                                                 [ 26%]
test.py::test_drop_column PASSED                                                                      [ 28%]
test.py::test_rename_column PASSED                                                                    [ 31%]
test.py::test_rename_two_columns PASSED                                                               [ 34%]
test.py::test_rename_table_and_column PASSED                                                          [ 36%]
test.py::test_rename_weird_spacing PASSED                                                             [ 39%]
test.py::test_ambiguous_rename_column PASSED                                                          [ 42%]
test.py::test_ambiguous_rename_table PASSED                                                           [ 44%]
test.py::test_change_column_def PASSED                                                                [ 47%]
test.py::test_add_not_null PASSED                                                                     [ 50%]
test.py::test_add_not_null_with_default PASSED                                                        [ 52%]
test.py::test_add_view PASSED                                                                         [ 55%]
test.py::test_drop_view PASSED                                                                        [ 57%]
test.py::test_drop_table_with_view PASSED                                                             [ 60%]
test.py::test_add_unique PASSED                                                                       [ 63%]
test.py::test_add_multi_column_unique PASSED                                                          [ 65%]
test.py::test_add_column_and_multi_column_unique PASSED                                               [ 68%]
test.py::test_drop_unique_no_apply PASSED                                                             [ 71%]
test.py::test_drop_unique PASSED                                                                      [ 73%]
test.py::test_parse_create_table PASSED                                                               [ 76%]
test.py::test_parse_create_table_with_comment PASSED                                                  [ 78%]
test.py::test_parse_create_table_with_comments PASSED                                                 [ 81%]
test.py::test_parse_create_table_with_table_comment PASSED                                            [ 84%]
test.py::test_parse_create_table_with_table_comment2 PASSED                                           [ 86%]
test.py::test_parse_create_table_with_inner_comment PASSED                                            [ 89%]
test.py::test_add_table2 PASSED                                                                       [ 92%]
test.py::test_json_column PASSED                                                                      [ 94%]
test.py::test_change_text_to_json PASSED                                                              [ 97%]
test.py::test_read_files PASSED                                                                       [100%]

============================================ 38 passed in 0.07s =============================================
```



