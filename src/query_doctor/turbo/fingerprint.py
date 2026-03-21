"""Query tree fingerprinting for the SQL compilation cache.

Computes a structural fingerprint of a Django ORM Query object by walking
the WHERE tree, SELECT columns, JOINs, ORDER BY, GROUP BY, annotations,
and other structural metadata — excluding parameter values. The fingerprint
is a blake2b hash that identifies query structure for cache lookups.
"""

from __future__ import annotations

import hashlib
from typing import Any

from django.db.models.lookups import Lookup
from django.db.models.sql import Query
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.where import WhereNode


def compute_fingerprint(query: Query, compiler: SQLCompiler) -> str:
    """Compute a structural fingerprint of a Query tree.

    The fingerprint captures the query's structural identity (model, fields,
    lookups, joins, ordering, etc.) without any user-supplied parameter values.
    Two queries with identical structure but different parameter values will
    produce the same fingerprint.

    Args:
        query: The Django ORM Query object.
        compiler: The SQLCompiler instance (provides connection/db info).

    Returns:
        A hex string (32 chars) from blake2b with 16-byte digest.
    """
    parts: list[str] = []

    # Database identity
    parts.append(f"vendor:{compiler.connection.vendor}")
    parts.append(f"using:{compiler.using}")

    # Model identity
    model = query.model
    if model is None:
        parts.append("model:unknown")
    else:
        parts.append(f"model:{model._meta.label}")

    # Compiler class
    parts.append(f"compiler:{type(compiler).__name__}")

    # DISTINCT
    if query.distinct:
        parts.append("distinct:true")
        if query.distinct_fields:
            parts.append(f"distinct_fields:{','.join(query.distinct_fields)}")

    # SELECT FOR UPDATE
    if getattr(query, "select_for_update", False):
        parts.append("for_update:true")
        if getattr(query, "select_for_update_nowait", False):
            parts.append("for_update_nowait:true")
        if getattr(query, "select_for_update_skip_locked", False):
            parts.append("for_update_skip_locked:true")
        sfu_of = getattr(query, "select_for_update_of", ())
        if sfu_of:
            parts.append(f"for_update_of:{','.join(sorted(sfu_of))}")

    # SELECT columns
    _fingerprint_select(query, parts)

    # WHERE tree
    if query.where:
        _fingerprint_where(query.where, parts)

    # JOINs
    _fingerprint_joins(query, parts)

    # ORDER BY
    _fingerprint_order_by(query, parts)

    # GROUP BY
    if query.group_by is not None:
        parts.append("group_by:true")

    # Annotations
    _fingerprint_annotations(query, parts)

    # LIMIT/OFFSET existence (not actual values)
    if query.low_mark:
        parts.append("offset:true")
    if query.high_mark is not None:
        parts.append("limit:true")

    # Select related
    if query.select_related:
        if isinstance(query.select_related, dict):
            parts.append(f"select_related:{_sorted_dict_repr(query.select_related)}")
        else:
            parts.append("select_related:true")

    fingerprint_str = "|".join(parts)
    return hashlib.blake2b(
        fingerprint_str.encode("utf-8"), digest_size=16
    ).hexdigest()


def _fingerprint_select(query: Query, parts: list[str]) -> None:
    """Fingerprint SELECT column list."""
    if query.select:
        col_names: list[str] = []
        for col in query.select:
            try:
                target = getattr(col, "target", None)
                if target is not None:
                    col_names.append(
                        f"{target.model._meta.label}.{target.column}"
                    )
                elif hasattr(col, "output_field"):
                    col_names.append(str(col.output_field))
                else:
                    col_names.append(str(type(col).__name__))
            except AttributeError:
                col_names.append(str(type(col).__name__))
        parts.append(f"select:{','.join(col_names)}")

    if query.values_select:
        parts.append(f"values_select:{','.join(query.values_select)}")


def _fingerprint_where(node: WhereNode, parts: list[str], depth: int = 0) -> None:
    """Walk the WHERE tree recursively, capturing structure without values.

    For Lookup nodes: captures (lookup_name, lhs field path) but NOT rhs value.
    For WhereNode connectors: captures (connector, negated).
    """
    prefix = f"where[{depth}]"
    parts.append(f"{prefix}:connector={node.connector},negated={node.negated}")

    for child in node.children:
        if isinstance(child, WhereNode):
            _fingerprint_where(child, parts, depth + 1)
        elif isinstance(child, Lookup):
            _fingerprint_lookup(child, parts, depth)
        else:
            # Unknown node type — include class name for safety
            parts.append(f"{prefix}:unknown={type(child).__name__}")


def _fingerprint_lookup(lookup: Lookup, parts: list[str], depth: int) -> None:  # type: ignore[type-arg]
    """Fingerprint a single Lookup node.

    For ``__in`` lookups the RHS length is included because different list
    sizes produce different SQL templates (``IN (%s,%s)`` vs
    ``IN (%s,%s,%s)``).
    """
    prefix = f"where[{depth}]"
    lookup_name = lookup.lookup_name

    # Get the LHS field path
    lhs_path = _get_field_path(lookup.lhs)

    parts.append(f"{prefix}:lookup={lookup_name},lhs={lhs_path}")

    # __in lookups: different list lengths produce different SQL placeholders
    if lookup_name == "in":
        rhs = lookup.rhs
        if isinstance(rhs, (list, tuple)):
            parts.append(f"{prefix}:in_count={len(rhs)}")
        elif hasattr(rhs, "query"):
            # Subquery — SQL structure depends on the inner query
            parts.append(f"{prefix}:in_subquery")


def _get_field_path(expression: Any) -> str:
    """Extract the field path from a lookup's LHS expression."""
    try:
        # Col object has target attribute with model and column
        if hasattr(expression, "target") and hasattr(expression, "alias"):
            target = expression.target
            model_label = target.model._meta.label if target.model else "?"
            return f"{model_label}.{target.column}"
    except (AttributeError, TypeError):
        pass

    # Fallback: use the expression type name
    return type(expression).__name__


def _fingerprint_joins(query: Query, parts: list[str]) -> None:
    """Fingerprint JOIN clauses."""
    if not hasattr(query, "alias_map"):
        return

    join_parts: list[str] = []
    for alias, join in query.alias_map.items():
        try:
            join_parts.append(
                f"{join.table_name}:{join.join_type}"
            )
        except AttributeError:
            join_parts.append(f"{alias}:{type(join).__name__}")

    if join_parts:
        join_parts.sort()  # Deterministic ordering
        parts.append(f"joins:{','.join(join_parts)}")


def _fingerprint_order_by(query: Query, parts: list[str]) -> None:
    """Fingerprint ORDER BY clause."""
    if query.order_by:
        parts.append(f"order_by:{','.join(str(o) for o in query.order_by)}")
    if query.extra_order_by:
        parts.append(f"extra_order_by:{','.join(str(o) for o in query.extra_order_by)}")


def _fingerprint_annotations(query: Query, parts: list[str]) -> None:
    """Fingerprint annotation names, types, and source expressions.

    Includes source field references so that annotations with the same name
    and type but different targets (e.g. ``Count('orders')`` vs
    ``Count('reviews')``) produce different fingerprints.
    """
    if query.annotations:
        ann_parts: list[str] = []
        for name, annotation in sorted(query.annotations.items()):
            ann_desc = f"{name}:{type(annotation).__name__}"
            # Include source expression field references
            source_refs = _get_expression_refs(annotation)
            if source_refs:
                ann_desc += f"({','.join(source_refs)})"
            ann_parts.append(ann_desc)
        parts.append(f"annotations:{','.join(ann_parts)}")


def _get_expression_refs(expr: Any) -> list[str]:
    """Collect field references from an expression tree.

    Returns a list of stable identifiers for the expression's source fields
    (e.g. column names or field attribute names) so that annotations
    targeting different fields produce different fingerprints.
    """
    refs: list[str] = []
    if hasattr(expr, "get_source_expressions"):
        for source in expr.get_source_expressions():
            if source is None:
                continue
            # Col-like: has a target with column name
            target = getattr(source, "target", None)
            if target is not None:
                col_name = getattr(target, "column", None)
                if col_name:
                    refs.append(str(col_name))
                    continue
            # F-like or named reference
            src_name = getattr(source, "name", None)
            if src_name:
                refs.append(str(src_name))
                continue
            # Recurse into nested expressions
            nested = _get_expression_refs(source)
            refs.extend(nested)
    return refs


def _sorted_dict_repr(d: dict[str, Any]) -> str:
    """Create a stable string representation of a nested dict."""
    items: list[str] = []
    for key in sorted(d.keys()):
        val = d[key]
        if isinstance(val, dict):
            items.append(f"{key}:{{{_sorted_dict_repr(val)}}}")
        else:
            items.append(f"{key}:{val}")
    return ",".join(items)
