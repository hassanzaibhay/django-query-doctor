"""Extract query parameters from a Django Query tree WITHOUT calling as_sql().

This module walks the Query's expression tree in the exact same order that
SQLCompiler.as_sql() would, collecting only parameter values. This is
significantly faster than full as_sql() because it skips:
- SQL string construction and concatenation
- Column name quoting
- JOIN clause building
- Alias resolution
- GROUP BY / ORDER BY SQL generation

CORRECTNESS INVARIANT: The params returned by extract_params() must be in
the EXACT same order as the params returned by as_sql(). If they ever
differ, the cache entry is demoted to UNTRUSTED and as_sql() is called
for validation.
"""

from __future__ import annotations

import logging
from typing import Any

from query_doctor.exceptions import QueryDoctorError

logger = logging.getLogger("query_doctor.turbo")


class ParamExtractionError(QueryDoctorError):
    """Raised when parameter extraction from the Query tree fails."""


def extract_params(query: Any, compiler: Any) -> tuple[Any, ...]:
    """Extract parameter values from a Query tree without full SQL compilation.

    Walks the query tree in the same order as SQLCompiler.as_sql():
    1. Extra SELECT params (query.extra_select)
    2. SELECT expression params (annotations in select)
    3. WHERE clause params
    4. HAVING clause params
    5. Extra WHERE params
    6. Subquery combinator params (excluded by cacheability check)

    Args:
        query: Django Query object.
        compiler: SQLCompiler instance (needed for expression context).

    Returns:
        Tuple of parameter values in SQL placeholder order.

    Raises:
        ParamExtractionError: If extraction encounters an unexpected tree structure.
    """
    params: list[Any] = []

    try:
        # 1. Extra SELECT params (from .extra(select={...}))
        # These should not exist (we skip .extra() queries), but handle gracefully
        if query.extra_select:
            for _, (_, extra_params) in query.extra_select.items():
                if extra_params:
                    params.extend(extra_params)

        # 2. Annotation params in SELECT
        # SQLCompiler.get_select() processes annotations that appear in SELECT
        _collect_select_params(query, compiler, params)

        # 3. WHERE clause params
        if query.where:
            _collect_where_params(query.where, compiler, params)

        # 4. Extra WHERE params (from .extra(where=[...]))
        if hasattr(query, "extra_where") and query.extra_where:
            for _, extra_params in query.extra_where:
                if extra_params:
                    params.extend(extra_params)

        # 5. HAVING params
        # In some Django versions, HAVING may be separate from WHERE.
        if hasattr(query, "having") and query.having and query.having is not query.where:
            _collect_where_params(query.having, compiler, params)

        return tuple(params)

    except ParamExtractionError:
        raise
    except Exception as e:
        raise ParamExtractionError(f"Failed to extract params: {e}") from e


def _collect_select_params(query: Any, compiler: Any, params: list[Any]) -> None:
    """Collect params from SELECT expressions (annotations).

    Mirrors SQLCompiler.get_select() param collection.
    Only annotations that are in the SELECT clause contribute params.
    """
    if not hasattr(query, "annotation_select") or not query.annotation_select:
        return

    for alias in query.annotation_select:
        annotation = query.annotations.get(alias)
        if annotation is not None:
            _collect_expression_params(annotation, compiler, params)


def _collect_where_params(where_node: Any, compiler: Any, params: list[Any]) -> None:
    """Recursively collect params from a WhereNode tree.

    Walks children in the same order as WhereNode.as_sql().
    For each Lookup child, extracts the RHS value(s).
    For each nested WhereNode, recurses.
    """
    for child in where_node.children:
        if hasattr(child, "children"):
            # Nested WhereNode (AND/OR group)
            _collect_where_params(child, compiler, params)
        elif hasattr(child, "rhs") and hasattr(child, "lhs"):
            # This is a Lookup node
            _collect_lookup_params(child, compiler, params)
        elif hasattr(child, "as_sql"):
            # Some other expression node — collect via expression walking
            _collect_expression_params(child, compiler, params)
        else:
            logger.debug("Unknown WHERE child type: %s", type(child).__name__)


def _collect_lookup_params(lookup: Any, compiler: Any, params: list[Any]) -> None:
    """Extract params from a Lookup node (e.g., Exact, In, Contains).

    Uses the lookup's own as_sql() method to get the exact same params
    that the full SQL compilation would produce. This handles all
    value transformations (e.g., __contains wrapping with %, isnull
    discarding the param, etc.).

    This is cheaper than full compiler.as_sql() because it only compiles
    a single WHERE clause node, not the entire query.
    """
    try:
        _sql, lookup_params = lookup.as_sql(compiler, compiler.connection)
        if lookup_params:
            params.extend(lookup_params)
    except Exception:
        # Fallback: manual extraction (less accurate but better than failing)
        _collect_lookup_params_fallback(lookup, compiler, params)


def _collect_lookup_params_fallback(lookup: Any, compiler: Any, params: list[Any]) -> None:
    """Fallback param extraction when process_lhs/process_rhs fails.

    Manually walks the lookup's LHS and RHS expressions.
    """
    # LHS params (rare — only when LHS is an expression, not a simple field)
    lhs = lookup.lhs
    if lhs is not None and _is_parameterized_expression(lhs):
        _collect_expression_params(lhs, compiler, params)

    # RHS params
    rhs = lookup.rhs
    if rhs is None:
        if hasattr(lookup, "lookup_name") and lookup.lookup_name == "isnull":
            return
        params.append(rhs)
    elif hasattr(rhs, "as_sql"):
        _collect_expression_params(rhs, compiler, params)
    elif isinstance(rhs, (list, tuple)):
        for item in rhs:
            if hasattr(item, "as_sql"):
                _collect_expression_params(item, compiler, params)
            else:
                params.append(item)
    else:
        params.append(rhs)


def _is_parameterized_expression(expr: Any) -> bool:
    """Check if an expression potentially contributes params.

    Simple column references (Col) don't contribute params.
    Returns True for expressions that might have embedded values.
    """
    from django.db.models.expressions import Col

    if isinstance(expr, Col):
        return False
    # If it has source expressions or is a Value, it might have params
    return hasattr(expr, "get_source_expressions") or hasattr(expr, "value")


def _collect_expression_params(expr: Any, compiler: Any, params: list[Any]) -> None:
    """Collect params from an arbitrary expression.

    Expressions have a tree structure via get_source_expressions().
    Leaf nodes that contribute params are typically Value() instances.
    Field references (Col, Ref) don't contribute params.
    """
    if expr is None:
        return

    from django.db.models.expressions import Col, Value

    # Value node — leaf with a param
    if isinstance(expr, Value):
        params.append(expr.value)
        return

    # Col — field reference, no params
    if isinstance(expr, Col):
        return

    # When node — condition is a Q object which needs special handling
    from django.db.models.expressions import When

    if isinstance(expr, When):
        # Use as_sql() on the When node to get exact params
        try:
            _sql, when_params = expr.as_sql(compiler, compiler.connection)
            if when_params:
                params.extend(when_params)
        except Exception:
            # Fallback: recurse into source expressions
            for source in expr.get_source_expressions():
                if source is not None:
                    _collect_expression_params(source, compiler, params)
        return

    # For other expressions, recurse into source expressions
    if hasattr(expr, "get_source_expressions"):
        for source in expr.get_source_expressions():
            if source is not None:
                _collect_expression_params(source, compiler, params)
