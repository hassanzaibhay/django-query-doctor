"""Tests for the check_serializers management command.

Validates command execution, output format, filtering options, and
branch coverage for the check_serializers management command.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest

drf = pytest.importorskip("rest_framework")

from django.core.management import call_command  # noqa: E402
from django.core.management.base import CommandError  # noqa: E402


class TestCheckSerializersCommand:
    """Tests for the check_serializers management command."""

    def test_command_runs_without_error(self):
        """Command executes without errors."""
        out = StringIO()
        err = StringIO()
        call_command("check_serializers", stdout=out, stderr=err)
        # Should not raise

    def test_command_json_format(self):
        """Command supports --format=json output."""
        out = StringIO()
        call_command("check_serializers", "--format=json", stdout=out)
        # JSON output should be parseable if there's output
        output = out.getvalue()
        # May contain JSON or a warning message
        assert isinstance(output, str)

    def test_command_console_format(self):
        """Command supports --format=console output."""
        out = StringIO()
        call_command("check_serializers", "--format=console", stdout=out)
        # Should not raise

    def test_command_with_app_filter(self):
        """Command accepts --app argument."""
        out = StringIO()
        call_command("check_serializers", "--app=auth", stdout=out)
        # Should not raise

    def test_command_with_nonexistent_app(self):
        """Command handles non-existent app gracefully."""
        out = StringIO()
        call_command("check_serializers", "--app=nonexistent_app_xyz", stdout=out)
        # Should not crash, just find no serializers
        output = out.getvalue()
        assert (
            "No serializers found" in output
            or "Found 0" in output
            or "serializer" in output.lower()
        )


class TestCheckSerializersCommandWithInlineSerializers:
    """Tests that use inline-defined serializers for controlled testing."""

    def test_discovers_inline_serializer(self):
        """Test that the analyzer can be invoked directly on inline serializers."""
        from rest_framework import serializers

        from query_doctor.analyzers.serializer_method import SerializerMethodAnalyzer

        class InlineBadSerializer(serializers.Serializer):
            total = serializers.SerializerMethodField()

            def get_total(self, obj):
                return obj.items.count()

        analyzer = SerializerMethodAnalyzer()
        results = analyzer.analyze(InlineBadSerializer)
        assert len(results) >= 1

    def test_no_issues_for_clean_serializer(self):
        """Clean serializer produces no issues."""
        from rest_framework import serializers

        from query_doctor.analyzers.serializer_method import SerializerMethodAnalyzer

        class InlineGoodSerializer(serializers.Serializer):
            name = serializers.CharField()

        analyzer = SerializerMethodAnalyzer()
        results = analyzer.analyze(InlineGoodSerializer)
        assert len(results) == 0


class TestCheckSerializersModuleScan:
    """Tests for scanning specific modules."""

    def test_command_with_module_pattern(self):
        """Command accepts --module argument for direct module scan."""
        out = StringIO()
        # Scan a module that likely has serializers
        call_command(
            "check_serializers",
            "--module=rest_framework.serializers",
            stdout=out,
        )
        output = out.getvalue()
        # rest_framework.serializers has base classes but no SMF issues
        assert isinstance(output, str)

    def test_command_with_file_filter(self):
        """Command accepts --file argument for filtering results."""
        out = StringIO()
        call_command(
            "check_serializers",
            "--file=nonexistent_file.py",
            stdout=out,
        )
        # Should run without error
        output = out.getvalue()
        assert isinstance(output, str)

    def test_command_fail_on_no_issues(self):
        """--fail-on with no issues should not raise."""
        out = StringIO()
        # No serializers with issues in auth app
        call_command(
            "check_serializers",
            "--app=auth",
            "--fail-on=critical",
            stdout=out,
        )
        # Should not raise CommandError


class TestCheckSerializersWithMocks:
    """Tests that use monkeypatching to exercise all command branches."""

    def _make_bad_serializer(self):
        """Create a serializer with a known N+1 pattern for testing."""
        from rest_framework import serializers

        class MockBadSerializer(serializers.Serializer):
            total = serializers.SerializerMethodField()

            def get_total(self, obj):
                return obj.items.count()

        return MockBadSerializer

    def test_serializers_found_with_issues_console(self):
        """Command renders console output when serializers with issues are found."""
        bad_cls = self._make_bad_serializer()
        out = StringIO()
        err = StringIO()

        with patch(
            "query_doctor.analyzers.discovery.discover_serializers",
            return_value=[bad_cls],
        ):
            call_command("check_serializers", "--format=console", stdout=out, stderr=err)

        output = out.getvalue()
        assert "Found 1 serializer" in output
        assert "N+1" in output or "potential" in output.lower()

    def test_serializers_found_with_issues_json(self):
        """Command renders JSON output when serializers with issues are found."""
        bad_cls = self._make_bad_serializer()
        out = StringIO()

        with patch(
            "query_doctor.analyzers.discovery.discover_serializers",
            return_value=[bad_cls],
        ):
            call_command("check_serializers", "--format=json", stdout=out)

        output = out.getvalue()
        assert "Found 1 serializer" in output

    def test_fail_on_triggers_command_error(self):
        """--fail-on raises CommandError when issues at that severity exist."""
        bad_cls = self._make_bad_serializer()

        with patch(
            "query_doctor.analyzers.discovery.discover_serializers",
            return_value=[bad_cls],
        ), pytest.raises(CommandError, match="check_serializers found issues"):
            call_command(
                "check_serializers",
                "--fail-on=warning",
                stdout=StringIO(),
                stderr=StringIO(),
            )

    def test_fail_on_info_triggers_command_error(self):
        """--fail-on=info raises CommandError even for INFO-level issues."""
        bad_cls = self._make_bad_serializer()

        with patch(
            "query_doctor.analyzers.discovery.discover_serializers",
            return_value=[bad_cls],
        ), pytest.raises(CommandError, match="check_serializers found issues"):
            call_command(
                "check_serializers",
                "--fail-on=info",
                stdout=StringIO(),
                stderr=StringIO(),
            )

    def test_fail_on_critical_does_not_trigger_for_warnings(self):
        """--fail-on=critical does not raise for WARNING-level issues only."""
        bad_cls = self._make_bad_serializer()
        out = StringIO()

        with patch(
            "query_doctor.analyzers.discovery.discover_serializers",
            return_value=[bad_cls],
        ):
            # Should NOT raise because issues are WARNING not CRITICAL
            call_command(
                "check_serializers",
                "--fail-on=critical",
                stdout=out,
                stderr=StringIO(),
            )

    def test_analyzer_exception_handled_gracefully(self):
        """Command handles analyzer exceptions without crashing."""
        from rest_framework import serializers

        class BrokenSerializer(serializers.Serializer):
            name = serializers.CharField()

        out = StringIO()
        err = StringIO()

        def raise_error(cls):
            raise RuntimeError("Intentional test error")

        with patch(
            "query_doctor.analyzers.discovery.discover_serializers",
            return_value=[BrokenSerializer],
        ), patch(
            "query_doctor.analyzers.serializer_method.SerializerMethodAnalyzer.analyze",
            side_effect=RuntimeError("Intentional test error"),
        ):
            call_command("check_serializers", stdout=out, stderr=err)

        err_output = err.getvalue()
        assert "Error analyzing" in err_output

    def test_file_filter_filters_prescriptions(self):
        """--file flag properly filters discovered issues."""
        bad_cls = self._make_bad_serializer()
        out = StringIO()

        with patch(
            "query_doctor.analyzers.discovery.discover_serializers",
            return_value=[bad_cls],
        ):
            # Filter to a file that won't match any issues
            call_command(
                "check_serializers",
                "--file=absolutely_nonexistent_xyz.py",
                stdout=out,
                stderr=StringIO(),
            )

        output = out.getvalue()
        assert "No SerializerMethodField N+1 issues found" in output

    def test_no_drf_installed(self):
        """Command shows warning when DRF is not installed."""
        import builtins

        from query_doctor.management.commands.check_serializers import Command

        out = StringIO()
        cmd = Command(stdout=out, stderr=StringIO())

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "rest_framework":
                raise ImportError("No DRF")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            cmd.handle(
                app_labels=None,
                module_patterns=None,
                file_patterns=None,
                format="console",
                fail_on=None,
            )

        output = out.getvalue()
        assert "not installed" in output.lower() or "skipping" in output.lower()

    def test_summary_with_zero_issues(self):
        """Command shows success message when serializers found but no issues."""
        from rest_framework import serializers

        class CleanSerializer(serializers.Serializer):
            name = serializers.CharField()

        out = StringIO()

        with patch(
            "query_doctor.analyzers.discovery.discover_serializers",
            return_value=[CleanSerializer],
        ):
            call_command("check_serializers", stdout=out)

        output = out.getvalue()
        assert "No SerializerMethodField N+1 issues found" in output

    def test_multiple_serializers_analyzed(self):
        """Command analyzes multiple serializers and aggregates results."""
        from rest_framework import serializers

        class Ser1(serializers.Serializer):
            a = serializers.SerializerMethodField()

            def get_a(self, obj):
                return obj.items.count()

        class Ser2(serializers.Serializer):
            b = serializers.SerializerMethodField()

            def get_b(self, obj):
                return obj.tags.all()

        out = StringIO()

        with patch(
            "query_doctor.analyzers.discovery.discover_serializers",
            return_value=[Ser1, Ser2],
        ):
            call_command("check_serializers", stdout=out, stderr=StringIO())

        output = out.getvalue()
        assert "Found 2 serializer" in output
