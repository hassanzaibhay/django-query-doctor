"""Tests for SQL fingerprinting in query_doctor.fingerprint."""

from __future__ import annotations

from query_doctor.fingerprint import extract_tables, fingerprint, normalize_sql


class TestNormalizeSql:
    """Tests for normalize_sql()."""

    def test_replace_integer_literals(self) -> None:
        sql = 'SELECT * FROM "book" WHERE "id" = 42'
        result = normalize_sql(sql)
        assert "42" not in result
        assert "?" in result

    def test_replace_string_literals_single_quotes(self) -> None:
        sql = 'SELECT * FROM "book" WHERE "title" = \'Django Unleashed\''
        result = normalize_sql(sql)
        assert "Django Unleashed" not in result
        assert "?" in result

    def test_replace_string_literals_double_quotes_values(self) -> None:
        # Double-quoted identifiers should remain, but double-quoted VALUES
        # in certain contexts get replaced
        sql = 'SELECT * FROM "book" WHERE "id" = 1'
        result = normalize_sql(sql)
        assert "?" in result

    def test_replace_float_literals(self) -> None:
        sql = 'SELECT * FROM "book" WHERE "price" > 19.99'
        result = normalize_sql(sql)
        assert "19.99" not in result

    def test_collapse_in_clause(self) -> None:
        sql = 'SELECT * FROM "book" WHERE "id" IN (1, 2, 3, 4, 5)'
        result = normalize_sql(sql)
        assert "in (?)" in result

    def test_collapse_in_clause_with_strings(self) -> None:
        sql = "SELECT * FROM \"book\" WHERE \"isbn\" IN ('123', '456', '789')"
        result = normalize_sql(sql)
        assert "in (?)" in result

    def test_collapse_whitespace(self) -> None:
        sql = 'SELECT   *   FROM   "book"   WHERE   "id"  =  1'
        result = normalize_sql(sql)
        assert "   " not in result

    def test_strip_trailing_semicolon(self) -> None:
        sql = 'SELECT * FROM "book";'
        result = normalize_sql(sql)
        assert not result.endswith(";")

    def test_lowercase(self) -> None:
        sql = 'SELECT * FROM "Book" WHERE "ID" = 1'
        result = normalize_sql(sql)
        assert result == result.lower()

    def test_replace_boolean_literals(self) -> None:
        sql = 'SELECT * FROM "book" WHERE "active" = TRUE'
        result = normalize_sql(sql)
        assert "true" not in result

    def test_newline_normalization(self) -> None:
        sql = 'SELECT *\nFROM "book"\nWHERE "id" = 1'
        result = normalize_sql(sql)
        assert "\n" not in result

    def test_complex_query(self) -> None:
        sql = (
            'SELECT "book"."id", "book"."title" '
            'FROM "testapp_book" '
            'INNER JOIN "testapp_author" ON ("book"."author_id" = "testapp_author"."id") '
            'WHERE "testapp_author"."name" = \'J.K. Rowling\' '
            "LIMIT 10"
        )
        result = normalize_sql(sql)
        assert "j.k. rowling" not in result
        assert "10" not in result
        assert "?" in result


class TestFingerprint:
    """Tests for fingerprint()."""

    def test_same_structure_different_params_same_fingerprint(self) -> None:
        sql1 = 'SELECT * FROM "book" WHERE "id" = 1'
        sql2 = 'SELECT * FROM "book" WHERE "id" = 42'
        assert fingerprint(sql1) == fingerprint(sql2)

    def test_different_tables_different_fingerprint(self) -> None:
        sql1 = 'SELECT * FROM "book" WHERE "id" = 1'
        sql2 = 'SELECT * FROM "author" WHERE "id" = 1'
        assert fingerprint(sql1) != fingerprint(sql2)

    def test_in_clause_normalization(self) -> None:
        sql1 = 'SELECT * FROM "book" WHERE "id" IN (1, 2, 3)'
        sql2 = 'SELECT * FROM "book" WHERE "id" IN (4, 5)'
        assert fingerprint(sql1) == fingerprint(sql2)

    def test_whitespace_normalization(self) -> None:
        sql1 = 'SELECT * FROM "book" WHERE "id" = 1'
        sql2 = 'SELECT  *  FROM  "book"  WHERE  "id"  =  1'
        assert fingerprint(sql1) == fingerprint(sql2)

    def test_fingerprint_is_hex_string(self) -> None:
        fp = fingerprint('SELECT * FROM "book"')
        assert len(fp) == 16
        # Should be valid hex
        int(fp, 16)

    def test_deterministic(self) -> None:
        sql = 'SELECT * FROM "book" WHERE "id" = 1'
        assert fingerprint(sql) == fingerprint(sql)


class TestExtractTables:
    """Tests for extract_tables()."""

    def test_simple_from(self) -> None:
        sql = 'SELECT * FROM "testapp_book"'
        assert extract_tables(sql) == ["testapp_book"]

    def test_from_with_alias(self) -> None:
        sql = 'SELECT * FROM "testapp_book" AS b'
        assert "testapp_book" in extract_tables(sql)

    def test_join(self) -> None:
        sql = (
            'SELECT * FROM "testapp_book" '
            'INNER JOIN "testapp_author" ON ("testapp_book"."author_id" = "testapp_author"."id")'
        )
        tables = extract_tables(sql)
        assert "testapp_book" in tables
        assert "testapp_author" in tables

    def test_multiple_joins(self) -> None:
        sql = (
            'SELECT * FROM "testapp_book" '
            'INNER JOIN "testapp_author" ON (1=1) '
            'LEFT JOIN "testapp_publisher" ON (1=1)'
        )
        tables = extract_tables(sql)
        assert len(tables) >= 3
        assert "testapp_book" in tables
        assert "testapp_author" in tables
        assert "testapp_publisher" in tables

    def test_no_tables(self) -> None:
        sql = "SELECT 1"
        assert extract_tables(sql) == []

    def test_subquery_from(self) -> None:
        sql = (
            'SELECT * FROM "testapp_book" WHERE "author_id" IN (SELECT "id" FROM "testapp_author")'
        )
        tables = extract_tables(sql)
        assert "testapp_book" in tables
        assert "testapp_author" in tables
