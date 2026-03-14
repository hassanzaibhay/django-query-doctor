"""SQL normalization and fingerprinting for query pattern detection.

Provides functions to normalize SQL queries (replacing literals with placeholders),
generate deterministic fingerprints for grouping similar queries, and extract
table names from SQL statements.
"""

from __future__ import annotations

import hashlib
import re

# Pre-compiled regex patterns for hot-path SQL normalization
_RE_QUOTED_STRING = re.compile(r"'(?:[^'\\]|\\.)*'")
_RE_PARAM_PLACEHOLDER = re.compile(r"%s")
_RE_TRUE = re.compile(r"\bTRUE\b", re.IGNORECASE)
_RE_FALSE = re.compile(r"\bFALSE\b", re.IGNORECASE)
_RE_NUMERIC = re.compile(r"\b\d+(?:\.\d+)?\b")
_RE_IN_CLAUSE = re.compile(r"\bIN\s*\([^)]*\)", re.IGNORECASE)
_RE_WHITESPACE = re.compile(r"\s+")
_RE_FROM_JOIN_TABLE = re.compile(r'(?:FROM|JOIN)\s+"?(\w+)"?', re.IGNORECASE)


def normalize_sql(sql: str) -> str:
    """Normalize a SQL query by replacing literals with placeholders.

    Replaces quoted strings, numbers, booleans, and IN-clause lists with '?',
    collapses whitespace, strips semicolons, and lowercases everything.
    """
    result = sql

    # Replace single-quoted strings (including escaped quotes inside)
    result = _RE_QUOTED_STRING.sub("?", result)

    # Replace Django-style %s parameter placeholders
    result = _RE_PARAM_PLACEHOLDER.sub("?", result)

    # Replace boolean literals (standalone TRUE/FALSE)
    result = _RE_TRUE.sub("?", result)
    result = _RE_FALSE.sub("?", result)

    # Replace numeric literals (integers and floats)
    # Must come after string replacement to avoid matching numbers inside strings
    result = _RE_NUMERIC.sub("?", result)

    # Collapse IN (...) lists to IN (?)
    result = _RE_IN_CLAUSE.sub("IN (?)", result)

    # Collapse whitespace (spaces, tabs, newlines) to single space
    result = _RE_WHITESPACE.sub(" ", result)

    # Strip trailing semicolons
    result = result.rstrip(";")

    # Strip leading/trailing whitespace
    result = result.strip()

    # Lowercase everything
    result = result.lower()

    return result


def fingerprint(sql: str) -> str:
    """Generate a SHA-256 fingerprint (first 16 hex chars) for a SQL query.

    Two queries with the same structure but different parameter values
    will produce the same fingerprint.
    """
    normalized = normalize_sql(sql)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def extract_tables(sql: str) -> list[str]:
    """Extract table names from FROM and JOIN clauses in a SQL query.

    Handles: FROM table, JOIN table, FROM table AS alias,
    FROM "quoted_table", and subqueries.
    Returns a deduplicated list of table names (without quotes or aliases).
    """
    # Match FROM or JOIN followed by a table name (optionally quoted)
    matches = _RE_FROM_JOIN_TABLE.findall(sql)

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for table in matches:
        if table not in seen:
            seen.add(table)
            result.append(table)

    return result
