"""
Validator for continuous validation and quality checks.

Provides validation logic for the T5 terminal to continuously check
build status, run tests, validate contracts, and detect file conflicts.
"""

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from .config import Config
from .contract_manager import Contract, ContractStatus


BuildStatus = Literal["success", "failed", "not_applicable"]
TestStatus = Literal["passed", "failed", "skipped", "not_applicable"]


@dataclass
class BuildResult:
    """Result of a build check."""

    status: BuildStatus
    project_path: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    output: str = ""
    error: str = ""
    duration_seconds: float = 0.0
    build_command: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "status": self.status,
            "project_path": self.project_path,
            "timestamp": self.timestamp,
            "output": self.output,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "build_command": self.build_command,
        }

    def is_success(self) -> bool:
        """Check if build succeeded."""
        return self.status == "success"


@dataclass
class TestResult:
    """Result of running tests."""

    status: TestStatus
    project_path: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    output: str = ""
    error: str = ""
    duration_seconds: float = 0.0
    failed_tests: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "status": self.status,
            "project_path": self.project_path,
            "timestamp": self.timestamp,
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "tests_skipped": self.tests_skipped,
            "output": self.output,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "failed_tests": self.failed_tests,
        }

    def is_success(self) -> bool:
        """Check if all tests passed."""
        return self.status == "passed" and self.tests_failed == 0


@dataclass
class ContractValidation:
    """Validation result for a contract."""

    contract_name: str
    is_valid: bool
    issues: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "contract_name": self.contract_name,
            "is_valid": self.is_valid,
            "issues": self.issues,
            "timestamp": self.timestamp,
        }


@dataclass
class Conflict:
    """Represents a file conflict between terminals."""

    file_path: str
    terminals: list[str]
    severity: Literal["warning", "critical"] = "warning"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "terminals": self.terminals,
            "severity": self.severity,
        }


class Validator:
    """
    Provides validation logic for continuous quality checks.

    The Validator is used primarily by the T5 (QA/Testing) terminal to
    continuously verify that the project builds, tests pass, contracts
    are implemented correctly, and no file conflicts exist.
    """

    def __init__(self, config: Config):
        """
        Initialize the Validator.

        Args:
            config: Orchestrator configuration
        """
        self.config = config

    def run_build_check(self, project_path: str | Path) -> BuildResult:
        """
        Run a build check on the project.

        Detects project type and runs appropriate build command:
        - Swift: swift build
        - Node.js: npm run build or npm install if no build script
        - Python: python -m py_compile (syntax check)

        Args:
            project_path: Path to the project directory

        Returns:
            BuildResult with status and output
        """
        project_dir = Path(project_path)

        if not project_dir.exists():
            return BuildResult(
                status="not_applicable",
                project_path=str(project_path),
                error=f"Project path does not exist: {project_path}",
            )

        # Detect project type and run appropriate build
        build_command = self._detect_build_command(project_dir)

        if not build_command:
            return BuildResult(
                status="not_applicable",
                project_path=str(project_path),
                error="Could not detect project type or build command",
            )

        # Run build
        start_time = datetime.now()

        try:
            result = subprocess.run(
                build_command,
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                shell=True,
            )

            duration = (datetime.now() - start_time).total_seconds()

            if result.returncode == 0:
                return BuildResult(
                    status="success",
                    project_path=str(project_path),
                    output=result.stdout,
                    duration_seconds=duration,
                    build_command=build_command,
                )
            else:
                return BuildResult(
                    status="failed",
                    project_path=str(project_path),
                    output=result.stdout,
                    error=result.stderr,
                    duration_seconds=duration,
                    build_command=build_command,
                )

        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            return BuildResult(
                status="failed",
                project_path=str(project_path),
                error="Build timed out after 5 minutes",
                duration_seconds=duration,
                build_command=build_command,
            )
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return BuildResult(
                status="failed",
                project_path=str(project_path),
                error=f"Build error: {str(e)}",
                duration_seconds=duration,
                build_command=build_command,
            )

    def _detect_build_command(self, project_dir: Path) -> str | None:
        """Detect the appropriate build command for the project."""
        # Check for Swift project
        if (project_dir / "Package.swift").exists():
            return "swift build"

        # Check for Node.js project
        if (project_dir / "package.json").exists():
            # Check if there's a build script
            try:
                import json

                package_json = json.loads((project_dir / "package.json").read_text())
                scripts = package_json.get("scripts", {})

                if "build" in scripts:
                    return "npm run build"
                else:
                    # Just install dependencies
                    return "npm install"
            except (json.JSONDecodeError, IOError):
                return "npm install"

        # Check for Python project
        if (project_dir / "setup.py").exists() or (project_dir / "pyproject.toml").exists():
            # Run syntax check on all .py files
            return 'find . -name "*.py" -type f -exec python -m py_compile {} \\;'

        # Check for any .py files
        py_files = list(project_dir.glob("**/*.py"))
        if py_files:
            return 'find . -name "*.py" -type f -exec python -m py_compile {} \\;'

        return None

    def validate_contracts(self, contracts: list[Contract]) -> list[ContractValidation]:
        """
        Validate that contracts are properly defined and implemented.

        This performs structural validation, not semantic validation.
        Checks:
        - Contract has required fields
        - Definition is not empty
        - If status is "implemented", implementer is set

        Args:
            contracts: List of contracts to validate

        Returns:
            List of ContractValidation results
        """
        validations = []

        for contract in contracts:
            issues = []

            # Check negotiation history is not empty (replaces old definition check)
            if not contract.history:
                issues.append("Contract has no negotiation history")

            # Check if implemented status has implementer
            if contract.status in (ContractStatus.IMPLEMENTED, ContractStatus.VERIFIED) and not contract.implementer:
                issues.append("Contract marked as implemented but no implementer specified")

            # Check contract has a name
            if not contract.name:
                issues.append("Contract name is empty")

            validations.append(
                ContractValidation(
                    contract_name=contract.name,
                    is_valid=len(issues) == 0,
                    issues=issues,
                )
            )

        return validations

    def run_tests(self, project_path: str | Path) -> TestResult:
        """
        Run tests for the project.

        Detects project type and runs appropriate test command:
        - Swift: swift test
        - Node.js: npm test
        - Python: pytest or python -m unittest

        Args:
            project_path: Path to the project directory

        Returns:
            TestResult with status and statistics
        """
        project_dir = Path(project_path)

        if not project_dir.exists():
            return TestResult(
                status="not_applicable",
                project_path=str(project_path),
                error=f"Project path does not exist: {project_path}",
            )

        # Detect test command
        test_command = self._detect_test_command(project_dir)

        if not test_command:
            return TestResult(
                status="not_applicable",
                project_path=str(project_path),
                error="Could not detect project type or test command",
            )

        # Run tests
        start_time = datetime.now()

        try:
            result = subprocess.run(
                test_command,
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                shell=True,
            )

            duration = (datetime.now() - start_time).total_seconds()

            # Parse output to extract test statistics
            test_result = self._parse_test_output(
                output=result.stdout,
                error=result.stderr,
                return_code=result.returncode,
                project_path=str(project_path),
                duration=duration,
            )

            return test_result

        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            return TestResult(
                status="failed",
                project_path=str(project_path),
                error="Tests timed out after 10 minutes",
                duration_seconds=duration,
            )
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return TestResult(
                status="failed",
                project_path=str(project_path),
                error=f"Test error: {str(e)}",
                duration_seconds=duration,
            )

    def _detect_test_command(self, project_dir: Path) -> str | None:
        """Detect the appropriate test command for the project."""
        # Check for Swift project
        if (project_dir / "Package.swift").exists():
            return "swift test"

        # Check for Node.js project
        if (project_dir / "package.json").exists():
            try:
                import json

                package_json = json.loads((project_dir / "package.json").read_text())
                scripts = package_json.get("scripts", {})

                if "test" in scripts:
                    return "npm test"
            except (json.JSONDecodeError, IOError):
                pass

        # Check for Python project with pytest
        if (project_dir / "pytest.ini").exists() or (project_dir / "pyproject.toml").exists():
            return "pytest"

        # Check for Python tests directory
        if (project_dir / "tests").exists() or (project_dir / "test").exists():
            return "python -m pytest || python -m unittest discover"

        return None

    def _parse_test_output(
        self,
        output: str,
        error: str,
        return_code: int,
        project_path: str,
        duration: float,
    ) -> TestResult:
        """Parse test output to extract statistics."""
        result = TestResult(
            status="failed" if return_code != 0 else "passed",
            project_path=project_path,
            output=output,
            error=error,
            duration_seconds=duration,
        )

        combined = output + error

        # Parse Swift test output
        if "Test Suite" in combined:
            # Swift format: "Executed 5 tests, with 0 failures"
            match = re.search(r"Executed (\d+) tests?, with (\d+) failures?", combined)
            if match:
                result.tests_run = int(match.group(1))
                result.tests_failed = int(match.group(2))
                result.tests_passed = result.tests_run - result.tests_failed

        # Parse pytest output
        elif "passed" in combined or "failed" in combined:
            # pytest format: "5 passed, 2 failed in 1.23s"
            match = re.search(r"(\d+) passed", combined)
            if match:
                result.tests_passed = int(match.group(1))

            match = re.search(r"(\d+) failed", combined)
            if match:
                result.tests_failed = int(match.group(1))

            match = re.search(r"(\d+) skipped", combined)
            if match:
                result.tests_skipped = int(match.group(1))

            result.tests_run = result.tests_passed + result.tests_failed + result.tests_skipped

        # Parse npm test output (often uses Jest)
        elif "Tests:" in combined:
            match = re.search(r"Tests:\s+(\d+) passed", combined)
            if match:
                result.tests_passed = int(match.group(1))

            match = re.search(r"(\d+) failed", combined)
            if match:
                result.tests_failed = int(match.group(1))

            result.tests_run = result.tests_passed + result.tests_failed

        # Extract failed test names
        if result.tests_failed > 0:
            result.failed_tests = self._extract_failed_test_names(combined)

        return result

    def _extract_failed_test_names(self, output: str) -> list[str]:
        """Extract names of failed tests from output."""
        failed_tests = []

        # Common patterns for failed test names
        patterns = [
            r"FAIL:\s+(.+)",  # pytest, unittest
            r"✗\s+(.+)",  # Swift
            r"FAILED\s+(.+)",  # pytest verbose
            r"Test case '(.+)' failed",  # Swift verbose
        ]

        for pattern in patterns:
            matches = re.findall(pattern, output)
            failed_tests.extend(matches[:10])  # Limit to 10

        return list(set(failed_tests))  # Deduplicate

    def check_file_conflicts(self, heartbeats: dict[str, dict]) -> list[Conflict]:
        """
        Detect file conflicts from terminal heartbeats.

        Args:
            heartbeats: Dictionary of terminal heartbeats from SyncManager

        Returns:
            List of Conflict objects for files touched by multiple terminals
        """
        file_map: dict[str, list[str]] = {}

        for terminal_id, heartbeat_data in heartbeats.items():
            if heartbeat_data.get("status") == "working":
                files_touched = heartbeat_data.get("files_touched", [])

                for file_path in files_touched:
                    if file_path not in file_map:
                        file_map[file_path] = []
                    file_map[file_path].append(terminal_id)

        # Create conflict objects for files touched by multiple terminals
        conflicts = []

        for file_path, terminals in file_map.items():
            if len(terminals) > 1:
                # Critical if same file, warning if just same directory
                severity = "critical" if len(terminals) > 1 else "warning"

                conflicts.append(
                    Conflict(
                        file_path=file_path,
                        terminals=terminals,
                        severity=severity,
                    )
                )

        return conflicts

    def get_validation_report(
        self,
        build_result: BuildResult | None = None,
        test_result: TestResult | None = None,
        contract_validations: list[ContractValidation] | None = None,
        conflicts: list[Conflict] | None = None,
    ) -> str:
        """
        Generate a comprehensive validation report.

        Args:
            build_result: Build check result
            test_result: Test execution result
            contract_validations: Contract validation results
            conflicts: File conflict detections

        Returns:
            Formatted markdown report
        """
        lines = ["# Validation Report\n"]
        lines.append(f"**Generated:** {datetime.now().isoformat()}\n")

        # Build Status
        if build_result:
            lines.append("## Build Status\n")

            status_emoji = {
                "success": "✅",
                "failed": "❌",
                "not_applicable": "➖",
            }

            emoji = status_emoji.get(build_result.status, "❓")
            lines.append(f"**Status:** {emoji} {build_result.status.upper()}")
            lines.append(f"**Command:** `{build_result.build_command}`")
            lines.append(f"**Duration:** {build_result.duration_seconds:.2f}s\n")

            if build_result.error:
                lines.append("**Error:**\n```")
                lines.append(build_result.error[:500])  # Limit output
                lines.append("```\n")

        # Test Status
        if test_result:
            lines.append("## Test Status\n")

            status_emoji = {
                "passed": "✅",
                "failed": "❌",
                "skipped": "⏭️",
                "not_applicable": "➖",
            }

            emoji = status_emoji.get(test_result.status, "❓")
            lines.append(f"**Status:** {emoji} {test_result.status.upper()}")
            lines.append(f"**Tests Run:** {test_result.tests_run}")
            lines.append(f"**Passed:** {test_result.tests_passed}")
            lines.append(f"**Failed:** {test_result.tests_failed}")
            lines.append(f"**Skipped:** {test_result.tests_skipped}")
            lines.append(f"**Duration:** {test_result.duration_seconds:.2f}s\n")

            if test_result.failed_tests:
                lines.append("**Failed Tests:**")
                for test_name in test_result.failed_tests[:5]:
                    lines.append(f"- {test_name}")
                lines.append("")

        # Contract Validations
        if contract_validations:
            lines.append("## Contract Validations\n")

            valid_count = sum(1 for v in contract_validations if v.is_valid)
            invalid_count = len(contract_validations) - valid_count

            lines.append(f"**Valid:** {valid_count}/{len(contract_validations)}")
            lines.append(f"**Invalid:** {invalid_count}\n")

            if invalid_count > 0:
                lines.append("**Issues:**\n")
                for validation in contract_validations:
                    if not validation.is_valid:
                        lines.append(f"- **{validation.contract_name}**")
                        for issue in validation.issues:
                            lines.append(f"  - {issue}")
                lines.append("")

        # File Conflicts
        if conflicts:
            lines.append("## File Conflicts\n")

            critical = [c for c in conflicts if c.severity == "critical"]
            warnings = [c for c in conflicts if c.severity == "warning"]

            if critical:
                lines.append(f"**Critical:** {len(critical)} conflicts")
                for conflict in critical[:5]:
                    terminals_str = ", ".join(conflict.terminals)
                    lines.append(f"- `{conflict.file_path}` - touched by {terminals_str}")
                lines.append("")

            if warnings:
                lines.append(f"**Warnings:** {len(warnings)} potential conflicts")

        # Summary
        lines.append("\n---\n")

        all_good = True

        if build_result and not build_result.is_success():
            all_good = False

        if test_result and not test_result.is_success():
            all_good = False

        if contract_validations and any(not v.is_valid for v in contract_validations):
            all_good = False

        if conflicts and any(c.severity == "critical" for c in conflicts):
            all_good = False

        if all_good:
            lines.append("✅ **All validations passed!**")
        else:
            lines.append("❌ **Some validations failed. See details above.**")

        return "\n".join(lines)
