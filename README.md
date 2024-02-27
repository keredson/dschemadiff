schema-diff
===========

Why?
----

I mean, Sqlite3 has `sqldiff --schema` right?  Well...


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

```
$ sqldiff --schema schema1.db schema2.db 
ALTER TABLE tbl ADD COLUMN b;
```

👏

```
$ sqldiff --schema schema2.db schema1.db 
DROP TABLE tbl; -- due to schema mismatch
CREATE TABLE tbl (
  a text
);
```

This is why I have trust issues... 🤯🤬


