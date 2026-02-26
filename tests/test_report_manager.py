"""
Tests for the Report Manager structured output system.

The ReportManager handles:
- Parsing terminal output into structured reports
- Saving/loading reports organized by terminal
- Providing cross-terminal context
- Summary index management
- JSON extraction from mixed text

All subprocess calls are mocked - never run real Claude CLI.
"""

import json
from unittest.mock import MagicMock, patch

from orchestrator.config import Config
from orchestrator.report_manager import Report, ReportManager


class TestReportDataclass:
    """Test Report creation, serialization, and rendering."""

    def test_to_dict_roundtrip(self) -> None:
        """Report should survive to_dict/from_dict cycle."""
        report = Report(
            id="report_001",
            task_id="task_001",
            terminal_id="t1",
            summary="Built login UI",
            files_created=["LoginView.swift"],
            files_modified=["App.swift"],
            components_created=["LoginView"],
            provides_to_others=[{"to": "t2", "what": "Login UI"}],
            dependencies_needed=[{"from": "t2", "what": "AuthService"}],
            next_steps=["Add validation"],
            blockers=[],
            success=True,
        )
        restored = Report.from_dict(report.to_dict())
        assert restored.id == "report_001"
        assert restored.summary == "Built login UI"
        assert restored.files_created == ["LoginView.swift"]
        assert restored.components_created == ["LoginView"]
        assert restored.provides_to_others[0]["to"] == "t2"

    def test_from_dict_defaults(self) -> None:
        """from_dict should provide defaults for missing fields."""
        data = {"id": "r1", "task_id": "t1"}
        report = Report.from_dict(data)
        assert report.terminal_id == "t2"  # Default
        assert report.summary == ""
        assert report.files_created == []
        assert report.success is True
        assert report.error is None

    def test_to_markdown_includes_all_sections(self) -> None:
        """Markdown output should include all populated sections."""
        report = Report(
            id="report_002",
            task_id="task_002",
            terminal_id="t1",
            summary="Full report",
            files_created=["A.swift"],
            files_modified=["B.swift"],
            components_created=["ComponentA"],
            provides_to_others=[{"to": "t2", "what": "API"}],
            dependencies_needed=[{"from": "t3", "what": "Docs"}],
            next_steps=["Polish UI"],
            blockers=["Missing API key"],
            success=True,
        )
        md = report.to_markdown()
        assert "Files Created" in md
        assert "Files Modified" in md
        assert "Components/APIs Exposed" in md
        assert "Available for Other Terminals" in md
        assert "Dependencies Needed" in md
        assert "Suggested Next Steps" in md
        assert "Blockers" in md
        assert "A.swift" in md

    def test_to_markdown_failed_report(self) -> None:
        """Failed report should show error in markdown."""
        report = Report(
            id="r3",
            task_id="t3",
            terminal_id="t2",
            summary="Failed",
            success=False,
            error="Timeout",
        )
        md = report.to_markdown()
        assert "Failed" in md
        assert "Timeout" in md

    def test_timestamp_auto_generated(self) -> None:
        """Report should auto-generate timestamp."""
        report = Report(id="r1", task_id="t1", terminal_id="t1")
        assert report.timestamp is not None
        assert "T" in report.timestamp


class TestReportManagerInit:
    """Test ReportManager directory setup."""

    def test_creates_report_dirs(self, config: Config) -> None:
        """Should create report dirs for all terminals + summary."""
        rm = ReportManager(config)
        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            assert (rm.reports_dir / tid).exists()
        assert (rm.reports_dir / "summary").exists()

    def test_report_id_generation(self, config: Config) -> None:
        """Generated IDs should be unique and start with report_."""
        rm = ReportManager(config)
        id1 = rm._generate_report_id()
        id2 = rm._generate_report_id()
        assert id1.startswith("report_")
        assert id2.startswith("report_")
        assert id1 != id2


class TestExtractJson:
    """Test JSON extraction from mixed text."""

    def test_clean_json(self, config: Config) -> None:
        """Should parse clean JSON directly."""
        rm = ReportManager(config)
        result = rm._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_markdown_code_block(self, config: Config) -> None:
        """Should strip markdown fences and parse JSON."""
        rm = ReportManager(config)
        text = '```json\n{"key": "value"}\n```'
        result = rm._extract_json(text)
        assert result == {"key": "value"}

    def test_json_embedded_in_text(self, config: Config) -> None:
        """Should extract JSON from surrounding text."""
        rm = ReportManager(config)
        text = 'Here is the result: {"summary": "done"} and some more text.'
        result = rm._extract_json(text)
        assert result is not None
        assert result["summary"] == "done"

    def test_no_json_returns_none(self, config: Config) -> None:
        """Text with no JSON should return None."""
        rm = ReportManager(config)
        assert rm._extract_json("No json here at all") is None

    def test_empty_input_returns_none(self, config: Config) -> None:
        """Empty input should return None."""
        rm = ReportManager(config)
        assert rm._extract_json("") is None

    def test_nested_json(self, config: Config) -> None:
        """Should handle nested JSON objects."""
        rm = ReportManager(config)
        text = '{"outer": {"inner": "value"}, "list": [1, 2]}'
        result = rm._extract_json(text)
        assert result is not None
        assert result["outer"]["inner"] == "value"


class TestParseOutputToReport:
    """Test output parsing into structured reports."""

    def test_failed_task_creates_error_report(self, config: Config) -> None:
        """Failed task should create minimal error report."""
        rm = ReportManager(config)
        report = rm.parse_output_to_report(
            output="Some output",
            task_id="task_001",
            task_title="Build UI",
            terminal_id="t1",
            success=False,
            error="Timeout",
        )
        assert report.success is False
        assert "Timeout" in report.summary
        assert report.error == "Timeout"

    def test_successful_parse_with_mocked_claude(self, config: Config) -> None:
        """Successful Claude parsing should populate all fields."""
        rm = ReportManager(config)
        parsed_json = json.dumps(
            {
                "summary": "Built login screen",
                "files_created": ["Login.swift"],
                "files_modified": [],
                "components_created": ["LoginView"],
                "provides_to_others": [{"to": "all", "what": "Login UI"}],
                "dependencies_needed": [],
                "next_steps": ["Add validation"],
                "blockers": [],
                "success": True,
            }
        )
        mock_result = MagicMock()
        mock_result.stdout = parsed_json

        with patch("subprocess.run", return_value=mock_result):
            report = rm.parse_output_to_report(
                output="Built the login screen with SwiftUI",
                task_id="task_001",
                task_title="Build Login",
                terminal_id="t1",
            )

        assert report.summary == "Built login screen"
        assert "Login.swift" in report.files_created
        assert "LoginView" in report.components_created

    def test_fallback_parse_on_claude_failure(self, config: Config) -> None:
        """Should use fallback parsing when Claude fails."""
        rm = ReportManager(config)

        with patch("subprocess.run", side_effect=Exception("No Claude")):
            report = rm.parse_output_to_report(
                output="Created LoginView.swift with form fields",
                task_id="task_001",
                task_title="Build Login",
                terminal_id="t1",
            )

        assert report.success is True
        assert report.id.startswith("report_")


class TestFallbackParse:
    """Test the regex-based fallback parser."""

    def test_extracts_created_files(self, config: Config) -> None:
        """Should extract file paths from create/wrote patterns."""
        rm = ReportManager(config)
        report = rm._fallback_parse(
            output="Created LoginView.swift and wrote Config.json",
            report_id="r1",
            task_id="t1",
            terminal_id="t1",
        )
        assert any("LoginView.swift" in f for f in report.files_created)

    def test_extracts_summary_from_first_line(self, config: Config) -> None:
        """Summary should come from first non-empty, non-header line."""
        rm = ReportManager(config)
        report = rm._fallback_parse(
            output="Built the complete login flow\nWith validation\nAnd tests",
            report_id="r1",
            task_id="t1",
            terminal_id="t1",
        )
        assert "Built the complete login flow" in report.summary

    def test_empty_output(self, config: Config) -> None:
        """Empty output should produce default summary."""
        rm = ReportManager(config)
        report = rm._fallback_parse(
            output="",
            report_id="r1",
            task_id="t1",
            terminal_id="t1",
        )
        assert report.summary == "Task completed"


class TestSaveAndLoadReports:
    """Test report persistence."""

    def test_save_creates_files(self, config: Config) -> None:
        """save_report should create JSON and MD files."""
        rm = ReportManager(config)
        report = Report(
            id="report_test_001",
            task_id="task_001",
            terminal_id="t1",
            summary="Test report",
        )
        path = rm.save_report(report)
        assert path.exists()
        assert (path.parent / "report_test_001.md").exists()

    def test_save_and_load_roundtrip(self, config: Config) -> None:
        """Saved report should be loadable via get_reports_for_terminal."""
        rm = ReportManager(config)
        report = Report(
            id="report_test_002",
            task_id="task_002",
            terminal_id="t2",
            summary="Roundtrip test",
            components_created=["ServiceA"],
        )
        rm.save_report(report)

        loaded = rm.get_reports_for_terminal("t2")
        assert len(loaded) == 1
        assert loaded[0].summary == "Roundtrip test"
        assert "ServiceA" in loaded[0].components_created

    def test_summary_index_updated(self, config: Config) -> None:
        """Summary index should track report metadata."""
        rm = ReportManager(config)
        report = Report(
            id="report_test_003",
            task_id="task_003",
            terminal_id="t1",
            summary="Index test",
            components_created=["CompA"],
            files_created=["a.swift"],
        )
        rm.save_report(report)

        index_file = rm.reports_dir / "summary" / "index.json"
        assert index_file.exists()

        data = json.loads(index_file.read_text())
        assert "t1" in data
        assert "CompA" in data["t1"]["components"]

    def test_get_reports_limit(self, config: Config) -> None:
        """get_reports_for_terminal should respect limit."""
        rm = ReportManager(config)
        for i in range(5):
            rm.save_report(
                Report(
                    id=f"report_limit_{i:03d}",
                    task_id=f"task_{i}",
                    terminal_id="t1",
                    summary=f"Report {i}",
                )
            )

        reports = rm.get_reports_for_terminal("t1", limit=3)
        assert len(reports) == 3

    def test_get_reports_empty_terminal(self, config: Config) -> None:
        """No reports for terminal should return empty list."""
        rm = ReportManager(config)
        assert rm.get_reports_for_terminal("t3") == []


class TestClearReports:
    """Test report cleanup."""

    def test_clear_single_terminal(self, config: Config) -> None:
        """clear_reports should remove single terminal's reports."""
        rm = ReportManager(config)
        rm.save_report(Report(id="r1", task_id="t1", terminal_id="t1", summary="test"))
        rm.save_report(Report(id="r2", task_id="t2", terminal_id="t2", summary="test"))

        rm.clear_reports("t1")

        assert rm.get_reports_for_terminal("t1") == []
        assert len(rm.get_reports_for_terminal("t2")) == 1

    def test_clear_all(self, config: Config) -> None:
        """clear_reports(None) should clear everything."""
        rm = ReportManager(config)
        rm.save_report(Report(id="r1", task_id="t1", terminal_id="t1", summary="test"))
        rm.save_report(Report(id="r2", task_id="t2", terminal_id="t2", summary="test"))

        rm.clear_reports(None)

        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            assert rm.get_reports_for_terminal(tid) == []  # type: ignore


class TestContextForTerminal:
    """Test cross-terminal context generation."""

    def test_context_from_other_terminals(self, config: Config) -> None:
        """Should include reports from other terminals that provide to target."""
        rm = ReportManager(config)
        rm.save_report(
            Report(
                id="r_context",
                task_id="t1",
                terminal_id="t2",
                summary="Built user model service",
                components_created=["UserService"],
                provides_to_others=[{"to": "t1", "what": "UserService API"}],
            )
        )

        context = rm.get_context_for_terminal("t1", "Build user profile UI")
        assert "UserService" in context

    def test_context_excludes_own_reports(self, config: Config) -> None:
        """Should not include target terminal's own reports."""
        rm = ReportManager(config)
        rm.save_report(
            Report(
                id="r_own",
                task_id="t1",
                terminal_id="t1",
                summary="Own report",
                components_created=["OwnComponent"],
                provides_to_others=[{"to": "t1", "what": "Self"}],
            )
        )

        context = rm.get_context_for_terminal("t1", "Build something")
        assert "OwnComponent" not in context

    def test_empty_context_when_no_reports(self, config: Config) -> None:
        """Should return empty string when no relevant reports exist."""
        rm = ReportManager(config)
        context = rm.get_context_for_terminal("t1", "Build something")
        assert context == ""


class TestAllComponents:
    """Test component tracking across terminals."""

    def test_get_all_components(self, config: Config) -> None:
        """Should return components from summary index."""
        rm = ReportManager(config)
        rm.save_report(
            Report(
                id="r1",
                task_id="t1",
                terminal_id="t1",
                summary="test",
                components_created=["ViewA"],
            )
        )
        rm.save_report(
            Report(
                id="r2",
                task_id="t2",
                terminal_id="t2",
                summary="test",
                components_created=["ServiceB"],
            )
        )

        components = rm.get_all_components()
        assert "ViewA" in components.get("t1", [])
        assert "ServiceB" in components.get("t2", [])

    def test_get_all_components_empty(self, config: Config) -> None:
        """Should return empty dict when no summary exists."""
        rm = ReportManager(config)
        assert rm.get_all_components() == {}
