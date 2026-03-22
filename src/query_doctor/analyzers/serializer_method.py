"""AST-based analyzer for DRF SerializerMethodField N+1 detection.

Statically analyzes DRF serializer source code using Python's ast module.
Detects get_<field> methods that may trigger database queries at serialization
time — the #1 hidden N+1 source in DRF apps.

Detection Patterns:
1. Related manager access on obj (e.g., obj.items.count())
2. QuerySet call inside method (e.g., Model.objects.filter())
3. Chained attribute access suggesting missing select_related (e.g., obj.author.name)
4. For loops iterating over querysets (e.g., for i in obj.items.all())

This is a STATIC analyzer — it reads source code, not runtime queries.
"""

from __future__ import annotations

import ast
import inspect
import logging
import textwrap
from typing import Any

from query_doctor.analyzers.base import BaseAnalyzer
from query_doctor.types import CallSite, CapturedQuery, IssueType, Prescription, Severity

logger = logging.getLogger("query_doctor")

# Known queryset methods that trigger database access
_QUERYSET_METHODS = frozenset(
    {
        "filter",
        "exclude",
        "get",
        "count",
        "exists",
        "all",
        "values",
        "values_list",
        "first",
        "last",
        "aggregate",
        "annotate",
        "order_by",
        "distinct",
        "select_related",
        "prefetch_related",
        "create",
        "update",
        "delete",
        "bulk_create",
        "bulk_update",
    }
)

# Known safe string/attribute methods that don't hit the DB
_SAFE_METHODS = frozenset(
    {
        "upper",
        "lower",
        "strip",
        "lstrip",
        "rstrip",
        "replace",
        "startswith",
        "endswith",
        "split",
        "join",
        "format",
        "encode",
        "decode",
        "title",
        "capitalize",
        "swapcase",
        "isnumeric",
        "isdigit",
        "isalpha",
        "isalnum",
        "items",
        "keys",
        "values",
        "get",
        "pop",
        "update",
        "append",
        "extend",
        "insert",
        "remove",
        "sort",
        "reverse",
        "__str__",
        "__repr__",
        "__len__",
    }
)


class SerializerMethodAnalyzer(BaseAnalyzer):
    """Analyzes DRF serializer classes for SerializerMethodField methods.

    Detects methods that may cause N+1 queries.
    This is a STATIC analyzer — it reads source code, not runtime queries.
    It should be invoked separately from the runtime query interception pipeline
    via the ``analyze_serializer()`` method.

    Inherits BaseAnalyzer for plugin API compatibility. The ``analyze()`` method
    (required by BaseAnalyzer) returns an empty list since this analyzer operates
    on serializer classes, not captured queries. Use ``analyze_serializer()``
    for actual analysis.
    """

    name = "serializer_method"

    def analyze(
        self,
        queries: list[CapturedQuery],
        models_meta: dict[str, Any] | None = None,
    ) -> list[Prescription]:
        """Conform to BaseAnalyzer interface. Returns empty list.

        This is a static analyzer that operates on serializer classes, not
        runtime queries. Use ``analyze_serializer()`` instead.

        Args:
            queries: Ignored — this analyzer does not use captured queries.
            models_meta: Ignored.

        Returns:
            Always an empty list.
        """
        return []

    def analyze_serializer(self, serializer_cls: Any) -> list[Prescription]:
        """Analyze a single serializer class for N+1 patterns.

        Finds all SerializerMethodField declarations, locates the corresponding
        get_<field> methods, parses them with ast, and walks the AST looking
        for dangerous patterns.

        Args:
            serializer_cls: A DRF serializer class to analyze.

        Returns:
            List of Prescription objects describing detected issues.
        """
        try:
            from rest_framework import serializers as drf_serializers
        except ImportError:
            logger.debug("DRF not installed, skipping SerializerMethodAnalyzer")
            return []

        prescriptions: list[Prescription] = []
        method_fields = self._find_method_fields(serializer_cls, drf_serializers)

        for field_name in method_fields:
            method_name = f"get_{field_name}"
            method = self._find_method(serializer_cls, method_name)
            if method is None:
                continue

            try:
                source = inspect.getsource(method)
                source = textwrap.dedent(source)
                tree = ast.parse(source)
            except (OSError, TypeError, SyntaxError):
                logger.debug(
                    "Could not parse source for %s.%s",
                    serializer_cls.__name__,
                    method_name,
                )
                continue

            # Determine the parameter name for the serialized object
            obj_param = self._get_obj_param(tree)
            if obj_param is None:
                continue

            try:
                source_file = inspect.getfile(method)
                source_lines = inspect.getsourcelines(method)
                start_line = source_lines[1]
            except (OSError, TypeError):
                source_file = "<unknown>"
                start_line = 0

            issues = self._walk_method(tree, obj_param, field_name, serializer_cls)
            for issue in issues:
                callsite = CallSite(
                    filepath=source_file,
                    line_number=start_line + issue.get("line_offset", 0),
                    function_name=method_name,
                    code_context=issue.get("code_context", ""),
                )
                prescriptions.append(
                    Prescription(
                        issue_type=IssueType.DRF_SERIALIZER,
                        severity=issue.get("severity", Severity.WARNING),
                        description=issue["description"],
                        fix_suggestion=issue["fix_suggestion"],
                        callsite=callsite,
                        extra={
                            "field": field_name,
                            "pattern": issue["pattern"],
                            "serializer": serializer_cls.__name__,
                        },
                    )
                )

        return prescriptions

    def _find_method_fields(self, serializer_cls: Any, drf_serializers: Any) -> list[str]:
        """Find all SerializerMethodField declarations on a serializer class.

        Args:
            serializer_cls: The serializer class to inspect.
            drf_serializers: The DRF serializers module.

        Returns:
            List of field names that are SerializerMethodField instances.
        """
        field_names: list[str] = []
        declared_fields = getattr(serializer_cls, "_declared_fields", {})
        for name, field_obj in declared_fields.items():
            if isinstance(field_obj, drf_serializers.SerializerMethodField):
                field_names.append(name)
        return field_names

    def _find_method(self, serializer_cls: Any, method_name: str) -> Any:
        """Find a method on the serializer class, following MRO.

        Args:
            serializer_cls: The serializer class.
            method_name: The method name to find (e.g., 'get_total').

        Returns:
            The method object, or None if not found.
        """
        for cls in inspect.getmro(serializer_cls):
            method = cls.__dict__.get(method_name)
            if method is not None and callable(method):
                return method
        return None

    def _get_obj_param(self, tree: ast.Module) -> str | None:
        """Extract the name of the serialized object parameter from a get_* method.

        The obj parameter is the second positional parameter (after self).

        Args:
            tree: The parsed AST of the method source.

        Returns:
            The parameter name (typically 'obj'), or None if malformed.
        """
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args.args
                if len(args) >= 2:
                    return args[1].arg
                return None
        return None

    def _walk_method(
        self,
        tree: ast.Module,
        obj_param: str,
        field_name: str,
        serializer_cls: Any,
    ) -> list[dict[str, Any]]:
        """Walk the AST of a get_<field> method looking for dangerous patterns.

        Args:
            tree: The parsed AST of the method.
            obj_param: The name of the serialized object parameter.
            field_name: The SerializerMethodField name.
            serializer_cls: The serializer class (for context in messages).

        Returns:
            List of issue dicts with description, fix_suggestion, pattern, etc.
        """
        issues: list[dict[str, Any]] = []

        for node in ast.walk(tree):
            # Pattern 1 & 2: Method calls
            if isinstance(node, ast.Call):
                issue = self._check_call(node, obj_param, field_name, serializer_cls)
                if issue is not None:
                    issues.append(issue)

            # Pattern 4: For loops with queryset iteration
            if isinstance(node, ast.For):
                issue = self._check_for_loop(node, obj_param, field_name, serializer_cls)
                if issue is not None:
                    issues.append(issue)

            # Pattern 5: Comprehensions iterating over querysets
            if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
                issue = self._check_comprehension(node, obj_param, field_name, serializer_cls)
                if issue is not None:
                    issues.append(issue)

            # Pattern 3: Deep attribute chain (obj.something.something_else)
            # Only check if it's NOT a method call target (avoid duplicates)
            if isinstance(node, ast.Attribute):
                # Skip if this attribute is the func of a Call node
                # We check this by seeing if the parent chain includes a Call
                issue = self._check_deep_chain(node, obj_param, field_name, serializer_cls, tree)
                if issue is not None:
                    issues.append(issue)

        return issues

    def _check_call(
        self,
        node: ast.Call,
        obj_param: str,
        field_name: str,
        serializer_cls: Any,
    ) -> dict[str, Any] | None:
        """Check a function call node for queryset method patterns.

        Detects:
        - obj.related.count() (Pattern 1: related manager access)
        - Model.objects.filter() (Pattern 2: direct queryset call)

        Args:
            node: The ast.Call node.
            obj_param: The object parameter name.
            field_name: The field name.
            serializer_cls: The serializer class.

        Returns:
            Issue dict or None.
        """
        func = node.func

        if not isinstance(func, ast.Attribute):
            return None

        method_name = func.attr

        # Check for obj.<related>.<queryset_method>()
        if isinstance(func.value, ast.Attribute) and method_name in _QUERYSET_METHODS:
            chain = self._get_attribute_chain(func)
            if chain and chain[0] == obj_param and len(chain) >= 3:
                related = chain[1]
                return {
                    "description": (
                        f"N+1 risk in {serializer_cls.__name__}.get_{field_name}(): "
                        f"'{obj_param}.{related}.{method_name}()' triggers a query per object"
                    ),
                    "fix_suggestion": (
                        f"Use queryset.annotate() or prefetch_related('{related}') "
                        f"instead of accessing '{related}' in the serializer method"
                    ),
                    "pattern": "related_manager_access",
                    "severity": Severity.WARNING,
                    "line_offset": getattr(node, "lineno", 1) - 1,
                    "code_context": ast.dump(node),
                }

        # Check for Model.objects.<method>() pattern
        if method_name in _QUERYSET_METHODS:
            chain = self._get_attribute_chain(func)
            if chain and len(chain) >= 3 and chain[-2] == "objects":
                model_name = chain[-3]
                return {
                    "description": (
                        f"N+1 risk in {serializer_cls.__name__}.get_{field_name}(): "
                        f"'{model_name}.objects.{method_name}()' executes a query per object"
                    ),
                    "fix_suggestion": (
                        f"Move the {model_name}.objects.{method_name}() call to the "
                        f"viewset queryset using annotate() or prefetch_related()"
                    ),
                    "pattern": "queryset_in_method",
                    "severity": Severity.WARNING,
                    "line_offset": getattr(node, "lineno", 1) - 1,
                    "code_context": ast.dump(node),
                }

        return None

    def _check_for_loop(
        self,
        node: ast.For,
        obj_param: str,
        field_name: str,
        serializer_cls: Any,
    ) -> dict[str, Any] | None:
        """Check a for loop for queryset iteration patterns.

        Detects: for item in obj.related.all()

        Args:
            node: The ast.For node.
            obj_param: The object parameter name.
            field_name: The field name.
            serializer_cls: The serializer class.

        Returns:
            Issue dict or None.
        """
        iter_node = node.iter

        # Check for obj.related.all() or obj.related_set.all()
        if isinstance(iter_node, ast.Call) and isinstance(iter_node.func, ast.Attribute):
            chain = self._get_attribute_chain(iter_node.func)
            if chain and chain[0] == obj_param and len(chain) >= 3:
                related = chain[1]
                method = chain[-1]
                if method in _QUERYSET_METHODS:
                    return {
                        "description": (
                            f"N+1 risk in {serializer_cls.__name__}"
                            f".get_{field_name}(): loop over "
                            f"'{obj_param}.{related}.{method}()' "
                            f"triggers a query per object"
                        ),
                        "fix_suggestion": (
                            f"Use prefetch_related('{related}') on the viewset queryset "
                            f"to batch-load related objects"
                        ),
                        "pattern": "loop_queryset",
                        "severity": Severity.WARNING,
                        "line_offset": getattr(node, "lineno", 1) - 1,
                        "code_context": "",
                    }

        # Check for obj.related_set (without .all() — implicit iteration)
        if isinstance(iter_node, ast.Attribute):
            chain = self._get_attribute_chain(iter_node)
            if chain and chain[0] == obj_param and len(chain) >= 2:
                related = chain[1]
                return {
                    "description": (
                        f"N+1 risk in {serializer_cls.__name__}.get_{field_name}(): "
                        f"loop over '{obj_param}.{related}' may trigger a query per object"
                    ),
                    "fix_suggestion": (
                        f"Use prefetch_related('{related}') on the viewset queryset"
                    ),
                    "pattern": "loop_queryset",
                    "severity": Severity.WARNING,
                    "line_offset": getattr(node, "lineno", 1) - 1,
                    "code_context": "",
                }

        return None

    def _check_comprehension(
        self,
        node: ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp,
        obj_param: str,
        field_name: str,
        serializer_cls: Any,
    ) -> dict[str, Any] | None:
        """Check a comprehension/generator for queryset iteration patterns.

        Detects: [x for x in obj.related.all()] and similar patterns
        in list comprehensions, set comprehensions, generator expressions,
        and dict comprehensions.

        Args:
            node: The comprehension AST node.
            obj_param: The object parameter name.
            field_name: The field name.
            serializer_cls: The serializer class.

        Returns:
            Issue dict or None.
        """
        for generator in node.generators:
            iter_node = generator.iter

            # Check for obj.related.all() or similar queryset call
            if isinstance(iter_node, ast.Call) and isinstance(iter_node.func, ast.Attribute):
                chain = self._get_attribute_chain(iter_node.func)
                if chain and chain[0] == obj_param and len(chain) >= 3:
                    related = chain[1]
                    method = chain[-1]
                    if method in _QUERYSET_METHODS:
                        comp_type = type(node).__name__
                        return {
                            "description": (
                                f"N+1 risk in {serializer_cls.__name__}.get_{field_name}(): "
                                f"comprehension over '{obj_param}.{related}.{method}()' "
                                f"triggers a query per object"
                            ),
                            "fix_suggestion": (
                                f"Use prefetch_related('{related}') on the viewset queryset "
                                f"to batch-load related objects"
                            ),
                            "pattern": "comprehension_queryset",
                            "severity": Severity.WARNING,
                            "line_offset": getattr(node, "lineno", 1) - 1,
                            "code_context": comp_type,
                        }

            # Check for obj.related (implicit iteration)
            if isinstance(iter_node, ast.Attribute):
                chain = self._get_attribute_chain(iter_node)
                if chain and chain[0] == obj_param and len(chain) >= 2:
                    related = chain[1]
                    comp_type = type(node).__name__
                    return {
                        "description": (
                            f"N+1 risk in {serializer_cls.__name__}.get_{field_name}(): "
                            f"comprehension over '{obj_param}.{related}' "
                            f"may trigger a query per object"
                        ),
                        "fix_suggestion": (
                            f"Use prefetch_related('{related}') on the viewset queryset"
                        ),
                        "pattern": "comprehension_queryset",
                        "severity": Severity.WARNING,
                        "line_offset": getattr(node, "lineno", 1) - 1,
                        "code_context": comp_type,
                    }

        return None

    def _check_deep_chain(
        self,
        node: ast.Attribute,
        obj_param: str,
        field_name: str,
        serializer_cls: Any,
        tree: ast.Module,
    ) -> dict[str, Any] | None:
        """Check for deep attribute chains suggesting missing select_related.

        Detects: obj.author.name (2+ deep chain on obj)

        Only flags chains that are NOT part of a queryset method call
        (those are caught by _check_call).

        Args:
            node: The ast.Attribute node.
            obj_param: The object parameter name.
            field_name: The field name.
            serializer_cls: The serializer class.
            tree: The full AST tree (for parent checking).

        Returns:
            Issue dict or None.
        """
        chain = self._get_attribute_chain(node)
        if not chain or chain[0] != obj_param:
            return None

        # Need at least obj.something.something_else (3 parts)
        if len(chain) < 3:
            return None

        # Skip if the last attr is a known queryset method (handled by _check_call)
        if chain[-1] in _QUERYSET_METHODS:
            return None

        # Skip if the last attr is a known safe method
        if chain[-1] in _SAFE_METHODS:
            return None

        # Skip if this node is the func target of a Call
        # (avoid flagging obj.items.count when _check_call handles obj.items.count())
        if self._is_call_func(node, tree):
            return None

        # Skip if intermediate attribute is 'objects' (Model.objects pattern)
        if "objects" in chain[1:]:
            return None

        related = chain[1]
        accessed = ".".join(chain[1:])
        return {
            "description": (
                f"Possible N+1 in {serializer_cls.__name__}.get_{field_name}(): "
                f"'{obj_param}.{accessed}' may trigger a query per object "
                f"if '{related}' is not select_related"
            ),
            "fix_suggestion": (f"Add select_related('{related}') to the viewset queryset"),
            "pattern": "deep_attribute_chain",
            "severity": Severity.INFO,
            "line_offset": getattr(node, "lineno", 1) - 1,
            "code_context": "",
        }

    def _get_attribute_chain(self, node: ast.AST) -> list[str]:
        """Extract the full attribute chain from a nested ast.Attribute node.

        For obj.author.name, returns ['obj', 'author', 'name'].

        Args:
            node: An ast.Attribute or ast.Name node.

        Returns:
            List of attribute names from left to right.
        """
        chain: list[str] = []
        current = node
        while isinstance(current, ast.Attribute):
            chain.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            chain.append(current.id)
        chain.reverse()
        return chain

    def _is_call_func(self, node: ast.Attribute, tree: ast.Module) -> bool:
        """Check if this Attribute node is the func target of a Call node.

        Args:
            node: The attribute node to check.
            tree: The full AST tree.

        Returns:
            True if node is used as Call.func somewhere.
        """
        for parent in ast.walk(tree):
            if isinstance(parent, ast.Call) and parent.func is node:
                return True
        return False
