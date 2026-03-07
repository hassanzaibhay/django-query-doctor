"""SQL normalization and fingerprinting for query pattern detection.

Provides functions to normalize SQL queries (replacing literals with placeholders),
generate deterministic fingerprints for grouping similar queries, and extract
table names from SQL statements.
"""
from __future__ import annotations

import hashlib
import re


def normalize_sql(sql: str) -> str:
    """Normalize a SQL query by replacing literals with placeholders.

    Replaces quoted strings, numbers, booleans, and IN-clause lists with '?',
    collapses whitespace, strips semicolons, and lowercases everything.
    """
    result = sql

    # Replace single-quoted strings (including escaped quotes inside)
    result = re.sub(r"'(?:[^'\\]|\\.)*'", "?", result)

    # Replace Django-style %s parameter placeholders
    result = re.sub(r"%s", "?", result)

    # Replace boolean literals (standalone TRUE/FALSE)
    result = re.sub(r"\bTRUE\b", "?", result, flags=re.IGNORECASE)
    result = re.sub(r"\bFALSE\b", "?", result, flags=re.IGNORECASE)

    # Replace numeric literals (integers and floats)
    # Must come after string replacement to avoid matching numbers inside strings
    result = re.sub(r"\b\d+(?:\.\d+)?\b", "?", result)

    # Collapse IN (...) lists to IN (?)
    result = re.sub(r"\bIN\s*\([^)]*\)", "IN (?)", result, flags=re.IGNORECASE)

    # Collapse whitespace (spaces, tabs, newlines) to single space
    result = re.sub(r"\s+", " ", result)

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
    pattern = r'(?:FROM|JOIN)\s+"?(\w+)"?'
    matches = re.findall(pattern, sql, flags=re.IGNORECASE)

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for table in matches:
        if table not in seen:
            seen.add(table)
            result.append(table)

    return result
