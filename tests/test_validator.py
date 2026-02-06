"""
Tests for the Validator continuous quality check system.

The Validator provides quality checks for the T5 terminal:
- Build detection and execution (mocked subprocess)
- Test runner with output parsing
- Contract structural validation
- File conflict detection from heartbeats
- Validation report generation

All subprocess calls are mocked - never run real builds.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from orchestrator.config import Config
from orchestrator.contract_manager import Contract, ContractManager, ContractStatus
from orchestrator.validator import (
    BuildResult,
    Conflict,
    ContractValidation,
    TestResult,
    Validator,
)


class TestBuildResultDataclass:
    """Test BuildResult creation and methods."""

    def test_to_dict_all_fields(self) -> None:
        """to_dict should include all fields."""
        result = BuildResult(
            status="success",
            project_path="/tmp/project",
            output="Build succeeded",
            duration_seconds=1.5,
            build_command="swift build",
        )
        d = result.to_dict()
        assert d["status"] == "success"
        assert d["project_path"] == "/tmp/project"
        assert d["build_command"] == "swift build"
        assert d["duration_seconds"] == 1.5

    def test_is_success_true(self) -> None:
        """is_success should return True for success status."""
        result = BuildResult(status="success", project_path="/tmp")
        assert result.is_success() is True

    def test_is_success_false_for_failed(self) -> None:
        """is_success should return False for failed status."""
        result = BuildResult(status="failed", project_path="/tmp")
        assert result.is_success() is False

    def test_is_success_false_for_not_applicable(self) -> None:
        """is_success should return False for not_applicable."""
        result = BuildResult(status="not_applicable", project_path="/tmp")
        assert result.is_success() is False


class TestTestResultDataclass:
    """Test TestResult creation and methods."""

    def test_to_dict_all_fields(self) -> None:
        """to_dict should include all fields including test counts."""
        result = TestResult(
            status="passed",
            project_path="/tmp",
            tests_run=10,
            tests_passed=9,
            tests_failed=1,
            tests_skipped=0,
            failed_tests=["test_something"],
        )
        d = result.to_dict()
        assert d["tests_run"] == 10
        assert d["tests_passed"] == 9
        assert d["tests_failed"] == 1
        assert d["failed_tests"] == ["test_something"]

    def test_is_success_all_passed(self) -> None:
        """is_success requires status=passed AND zero failures."""
        result = TestResult(status="passed", project_path="/tmp", tests_failed=0)
        assert result.is_success() is True

    def test_is_success_false_when_failures(self) -> None:
        """is_success should be False if tests_failed > 0 even if status is passed."""
        result = TestResult(status="passed", project_path="/tmp", tests_failed=1)
        assert result.is_success() is False

    def test_is_success_false_for_failed_status(self) -> None:
        """is_success should be False for failed status."""
        result = TestResult(status="failed", project_path="/tmp", tests_failed=0)
        assert result.is_success() is False


class TestContractValidationDataclass:
    """Test ContractValidation dataclass."""

    def test_to_dict(self) -> None:
        """to_dict should serialize correctly."""
        cv = ContractValidation(
            contract_name="UserService",
            is_valid=False,
            issues=["No implementer"],
        )
        d = cv.to_dict()
        assert d["contract_name"] == "UserService"
        assert d["is_valid"] is False
        assert d["issues"] == ["No implementer"]
        assert "timestamp" in d


class TestConflictDataclass:
    """Test Conflict dataclass."""

    def test_to_dict(self) -> None:
        """to_dict should serialize conflict info."""
        conflict = Conflict(
            file_path="User.swift",
            terminals=["t1", "t2"],
            severity="critical",
        )
        d = conflict.to_dict()
        assert d["file_path"] == "User.swift"
        assert d["terminals"] == ["t1", "t2"]
        assert d["severity"] == "critical"

    def test_default_severity_is_warning(self) -> None:
        """Default severity should be warning."""
        conflict = Conflict(file_path="a.py", terminals=["t1"])
        assert conflict.severity == "warning"


class TestBuildDetection:
    """Test build command detection for various project types."""

    def test_nonexistent_path(self, config: Config) -> None:
        """Nonexistent path should return not_applicable."""
        validator = Validator(config)
        result = validator.run_build_check("/nonexistent/path")
        assert result.status == "not_applicable"
        assert "does not exist" in result.error

    def test_detect_swift_project(self, config: Config, tmp_path: Path) -> None:
        """Should detect Swift project by Package.swift."""
        (tmp_path / "Package.swift").touch()
        validator = Validator(config)
        cmd = validator._detect_build_command(tmp_path)
        assert cmd == "swift build"

    def test_detect_node_with_build_script(self, config: Config, tmp_path: Path) -> None:
        """Should detect npm build when package.json has build script."""
        import json
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {"build": "tsc"}}))
        validator = Validator(config)
        cmd = validator._detect_build_command(tmp_path)
        assert cmd == "npm run build"

    def test_detect_node_without_build(self, config: Config, tmp_path: Path) -> None:
        """Should fall back to npm install when no build script."""
        import json
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {}}))
        validator = Validator(config)
        cmd = validator._detect_build_command(tmp_path)
        assert cmd == "npm install"

    def test_detect_python_project(self, config: Config, tmp_path: Path) -> None:
        """Should detect Python project by pyproject.toml."""
        (tmp_path / "pyproject.toml").touch()
        validator = Validator(config)
        cmd = validator._detect_build_command(tmp_path)
        assert "py_compile" in cmd

    def test_detect_no_project(self, config: Config, tmp_path: Path) -> None:
        """Should return None when no recognizable project."""
        validator = Validator(config)
        cmd = validator._detect_build_command(tmp_path)
        assert cmd is None

    def test_no_build_command_returns_not_applicable(self, config: Config, tmp_path: Path) -> None:
        """Empty dir with no project files -> not_applicable."""
        validator = Validator(config)
        result = validator.run_build_check(tmp_path)
        assert result.status == "not_applicable"

    def test_successful_build(self, config: Config, tmp_path: Path) -> None:
        """Mocked successful build should return success status."""
        (tmp_path / "Package.swift").touch()
        validator = Validator(config)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Build succeeded"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = validator.run_build_check(tmp_path)

        assert result.status == "success"
        assert result.output == "Build succeeded"
        assert result.build_command == "swift build"

    def test_failed_build(self, config: Config, tmp_path: Path) -> None:
        """Mocked failed build should return failed status."""
        (tmp_path / "Package.swift").touch()
        validator = Validator(config)

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: missing target"

        with patch("subprocess.run", return_value=mock_result):
            result = validator.run_build_check(tmp_path)

        assert result.status == "failed"
        assert "missing target" in result.error

    def test_build_timeout(self, config: Config, tmp_path: Path) -> None:
        """Timed-out build should return failed."""
        import subprocess as sp
        (tmp_path / "Package.swift").touch()
        validator = Validator(config)

        with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="swift build", timeout=300)):
            result = validator.run_build_check(tmp_path)

        assert result.status == "failed"
        assert "timed out" in result.error


class TestValidateContracts:
    """Test contract structural validation."""

    def test_valid_contract(self, config: Config, contract_manager: ContractManager) -> None:
        """Contract with history and proper fields should be valid."""
        validator = Validator(config)
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="UserService",
            contract_type="interface",
            content="User service API",
        )
        results = validator.validate_contracts([contract])
        assert len(results) == 1
        assert results[0].is_valid is True

    def test_empty_name_is_invalid(self, config: Config) -> None:
        """Contract with empty name should be invalid."""
        validator = Validator(config)
        contract = Contract(id="c1", name="", contract_type="interface", proposer="t1")
        results = validator.validate_contracts([contract])
        assert results[0].is_valid is False
        assert any("name is empty" in i for i in results[0].issues)

    def test_no_history_is_invalid(self, config: Config) -> None:
        """Contract with no negotiation history should be invalid."""
        validator = Validator(config)
        contract = Contract(id="c1", name="Test", contract_type="interface", proposer="t1")
        results = validator.validate_contracts([contract])
        assert results[0].is_valid is False
        assert any("no negotiation history" in i for i in results[0].issues)

    def test_implemented_without_implementer(self, config: Config) -> None:
        """Implemented contract without implementer should be invalid."""
        from orchestrator.contract_manager import NegotiationEntry
        validator = Validator(config)
        contract = Contract(
            id="c1",
            name="Test",
            contract_type="interface",
            proposer="t1",
            status=ContractStatus.IMPLEMENTED,
            history=[NegotiationEntry(
                terminal="t1",
                timestamp="2026-01-01T00:00:00",
                action="proposal",
                content="Test proposal",
            )],
        )
        results = validator.validate_contracts([contract])
        assert results[0].is_valid is False
        assert any("implementer" in i for i in results[0].issues)

    def test_empty_list_returns_empty(self, config: Config) -> None:
        """Empty contracts list should return empty validations."""
        validator = Validator(config)
        assert validator.validate_contracts([]) == []


class TestTestRunner:
    """Test the test runner with mocked subprocess."""

    def test_nonexistent_path(self, config: Config) -> None:
        """Nonexistent path should return not_applicable."""
        validator = Validator(config)
        result = validator.run_tests("/nonexistent")
        assert result.status == "not_applicable"

    def test_detect_swift_test(self, config: Config, tmp_path: Path) -> None:
        """Swift project should use swift test."""
        (tmp_path / "Package.swift").touch()
        validator = Validator(config)
        cmd = validator._detect_test_command(tmp_path)
        assert cmd == "swift test"

    def test_detect_pytest(self, config: Config, tmp_path: Path) -> None:
        """Python project with pyproject.toml should use pytest."""
        (tmp_path / "pyproject.toml").touch()
        validator = Validator(config)
        cmd = validator._detect_test_command(tmp_path)
        assert cmd == "pytest"

    def test_no_test_command(self, config: Config, tmp_path: Path) -> None:
        """No recognizable test setup should return not_applicable."""
        validator = Validator(config)
        result = validator.run_tests(tmp_path)
        assert result.status == "not_applicable"

    def test_parse_pytest_output(self, config: Config) -> None:
        """Should parse pytest-style output correctly."""
        validator = Validator(config)
        result = validator._parse_test_output(
            output="10 passed, 2 failed, 1 skipped in 0.5s",
            error="",
            return_code=1,
            project_path="/tmp",
            duration=0.5,
        )
        assert result.tests_passed == 10
        assert result.tests_failed == 2
        assert result.tests_skipped == 1
        assert result.tests_run == 13

    def test_parse_swift_test_output(self, config: Config) -> None:
        """Should parse Swift test output correctly."""
        validator = Validator(config)
        result = validator._parse_test_output(
            output="Test Suite 'All tests' started.\nExecuted 5 tests, with 1 failure",
            error="",
            return_code=1,
            project_path="/tmp",
            duration=2.0,
        )
        assert result.tests_run == 5
        assert result.tests_failed == 1
        assert result.tests_passed == 4

    def test_parse_jest_output(self, config: Config) -> None:
        """Should parse Jest/npm test output."""
        validator = Validator(config)
        result = validator._parse_test_output(
            output="Tests: 8 passed, 2 failed\nRan all test suites.",
            error="",
            return_code=1,
            project_path="/tmp",
            duration=3.0,
        )
        assert result.tests_passed == 8
        assert result.tests_failed == 2

    def test_extract_failed_test_names(self, config: Config) -> None:
        """Should extract failed test names from output."""
        validator = Validator(config)
        output = "FAIL: test_login_success\nFAIL: test_logout\nPASSED: test_other"
        names = validator._extract_failed_test_names(output)
        assert len(names) >= 2
        assert any("test_login_success" in n for n in names)


class TestFileConflictDetection:
    """Test file conflict detection from heartbeat data."""

    def test_no_conflicts(self, config: Config) -> None:
        """Different files across terminals should not conflict."""
        validator = Validator(config)
        heartbeats = {
            "t1": {"status": "working", "files_touched": ["A.swift"]},
            "t2": {"status": "working", "files_touched": ["B.swift"]},
        }
        conflicts = validator.check_file_conflicts(heartbeats)
        assert len(conflicts) == 0

    def test_detect_conflict(self, config: Config) -> None:
        """Same file in two working terminals is a conflict."""
        validator = Validator(config)
        heartbeats = {
            "t1": {"status": "working", "files_touched": ["User.swift"]},
            "t2": {"status": "working", "files_touched": ["User.swift"]},
        }
        conflicts = validator.check_file_conflicts(heartbeats)
        assert len(conflicts) == 1
        assert conflicts[0].file_path == "User.swift"
        assert set(conflicts[0].terminals) == {"t1", "t2"}

    def test_idle_excluded(self, config: Config) -> None:
        """Idle terminals should not trigger conflicts."""
        validator = Validator(config)
        heartbeats = {
            "t1": {"status": "working", "files_touched": ["User.swift"]},
            "t2": {"status": "idle", "files_touched": ["User.swift"]},
        }
        conflicts = validator.check_file_conflicts(heartbeats)
        assert len(conflicts) == 0

    def test_empty_heartbeats(self, config: Config) -> None:
        """Empty heartbeats dict should return no conflicts."""
        validator = Validator(config)
        assert validator.check_file_conflicts({}) == []


class TestValidationReport:
    """Test validation report generation."""

    def test_all_good_report(self, config: Config) -> None:
        """All passing should show all passed message."""
        validator = Validator(config)
        report = validator.get_validation_report(
            build_result=BuildResult(status="success", project_path="/tmp", build_command="swift build"),
            test_result=TestResult(status="passed", project_path="/tmp", tests_failed=0),
        )
        assert "All validations passed" in report

    def test_failed_build_in_report(self, config: Config) -> None:
        """Failed build should appear in report."""
        validator = Validator(config)
        report = validator.get_validation_report(
            build_result=BuildResult(status="failed", project_path="/tmp", error="Missing target"),
        )
        assert "FAILED" in report
        assert "Some validations failed" in report

    def test_invalid_contracts_in_report(self, config: Config) -> None:
        """Invalid contracts should appear in report."""
        validator = Validator(config)
        cv = ContractValidation(
            contract_name="BadContract", is_valid=False, issues=["No history"]
        )
        report = validator.get_validation_report(contract_validations=[cv])
        assert "BadContract" in report
        assert "No history" in report

    def test_conflicts_in_report(self, config: Config) -> None:
        """File conflicts should appear in report."""
        validator = Validator(config)
        conflict = Conflict(file_path="User.swift", terminals=["t1", "t2"], severity="critical")
        report = validator.get_validation_report(conflicts=[conflict])
        assert "User.swift" in report
        assert "t1" in report

    def test_empty_report(self, config: Config) -> None:
        """Report with no inputs should still be valid."""
        validator = Validator(config)
        report = validator.get_validation_report()
        assert "Validation Report" in report
        assert "All validations passed" in report
