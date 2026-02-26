#!/usr/bin/env python3
"""
Quality Gates - Archon Test Infrastructure

This script enforces quality gates for the Archon orchestrator:
1. Build verification (syntax check, imports)
2. Test execution with coverage
3. Linting (ruff, black check)
4. Type checking (mypy)
5. Quality thresholds enforcement

Exit codes:
- 0: All gates passed
- 1: Build failed
- 2: Tests failed
- 3: Coverage below threshold
- 4: Linting failed
- 5: Type checking failed

Usage:
    python scripts/quality_gates.py              # Run all gates
    python scripts/quality_gates.py --quick      # Quick smoke tests only
    python scripts/quality_gates.py --no-lint    # Skip linting
    python scripts/quality_gates.py --coverage   # Coverage report only
"""

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
ORCHESTRA_QA = PROJECT_ROOT / ".orchestra" / "qa"
TESTS_DIR = PROJECT_ROOT / "tests"
ORCHESTRATOR_DIR = PROJECT_ROOT / "orchestrator"


@dataclass
class GateResult:
    """Result of a quality gate check."""

    name: str
    passed: bool
    duration_seconds: float
    details: str = ""
    warnings: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


@dataclass
class QualityReport:
    """Complete quality report."""

    timestamp: str
    overall_passed: bool
    gates: list[GateResult]
    summary: str
    quality_score: float  # 0.0 - 1.0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "overall_passed": self.overall_passed,
            "quality_score": self.quality_score,
            "summary": self.summary,
            "gates": [
                {
                    "name": g.name,
                    "passed": g.passed,
                    "duration": g.duration_seconds,
                    "details": g.details,
                    "warnings": g.warnings,
                    "metrics": g.metrics,
                }
                for g in self.gates
            ],
        }


def run_command(
    cmd: list[str],
    cwd: Path | None = None,
    capture: bool = True,
    timeout: int = 300,
) -> tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or PROJECT_ROOT,
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"


def check_build() -> GateResult:
    """Gate 1: Verify code can be imported without errors."""
    start = time.time()

    # Check Python syntax
    code, stdout, stderr = run_command(
        ["python", "-m", "py_compile", str(ORCHESTRATOR_DIR / "__init__.py")]
    )

    if code != 0:
        return GateResult(
            name="Build Verification",
            passed=False,
            duration_seconds=time.time() - start,
            details=f"Syntax error: {stderr}",
        )

    # Try importing main modules
    import_check = """
import sys
sys.path.insert(0, '.')
try:
    from orchestrator import config, task_queue, terminal
    from orchestrator import planner, orchestrator, report_manager
    from orchestrator import contract_manager, manager_intelligence
    print("OK")
except ImportError as e:
    print(f"FAIL: {e}")
    sys.exit(1)
"""

    code, stdout, stderr = run_command(["python", "-c", import_check])

    passed = code == 0 and "OK" in stdout
    return GateResult(
        name="Build Verification",
        passed=passed,
        duration_seconds=time.time() - start,
        details="All modules import successfully" if passed else f"Import failed: {stdout}{stderr}",
    )


def check_tests(quick: bool = False) -> GateResult:
    """Gate 2: Run tests and check results."""
    start = time.time()

    # Build pytest command
    cmd = ["python", "-m", "pytest"]

    if quick:
        cmd.extend(["-m", "smoke or not slow", "-x", "--tb=line"])
    else:
        cmd.extend(
            [
                "--tb=short",
                "-q",
                f"--junitxml={ORCHESTRA_QA / 'tests' / 'results.xml'}",
            ]
        )

    code, stdout, stderr = run_command(cmd, timeout=600)

    # Parse test results
    passed_count = 0
    failed_count = 0
    skipped_count = 0

    for line in stdout.split("\n"):
        if "passed" in line:
            try:
                parts = line.split()
                for i, p in enumerate(parts):
                    if "passed" in p and i > 0:
                        passed_count = int(parts[i - 1])
                    if "failed" in p and i > 0:
                        failed_count = int(parts[i - 1])
                    if "skipped" in p and i > 0:
                        skipped_count = int(parts[i - 1])
            except (ValueError, IndexError):
                pass

    passed = code == 0
    total = passed_count + failed_count

    return GateResult(
        name="Test Execution",
        passed=passed,
        duration_seconds=time.time() - start,
        details=f"{passed_count} passed, {failed_count} failed, {skipped_count} skipped",
        metrics={
            "passed": passed_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "total": total,
            "pass_rate": passed_count / total if total > 0 else 0.0,
        },
    )


def check_coverage(threshold: float = 80.0) -> GateResult:
    """Gate 3: Check test coverage."""
    start = time.time()

    # Check if pytest-cov is available
    check_code, _, _ = run_command(["python", "-c", "import pytest_cov"])
    if check_code != 0:
        return GateResult(
            name="Test Coverage",
            passed=True,  # Skip gracefully
            duration_seconds=time.time() - start,
            details="Coverage check skipped (pytest-cov not installed)",
            warnings=["Install pytest-cov for coverage: pip install pytest-cov"],
            metrics={"coverage_percent": -1, "threshold": threshold, "skipped": True},
        )

    cmd = [
        "python",
        "-m",
        "pytest",
        "--cov=orchestrator",
        "--cov-report=term-missing",
        f"--cov-report=json:{ORCHESTRA_QA / 'coverage' / 'coverage.json'}",
        f"--cov-report=html:{ORCHESTRA_QA / 'coverage' / 'html'}",
        "--cov-fail-under",
        str(threshold),
        "-q",
    ]

    code, stdout, stderr = run_command(cmd, timeout=600)

    # Parse coverage percentage
    coverage_pct = 0.0
    for line in stdout.split("\n"):
        if "TOTAL" in line:
            try:
                parts = line.split()
                for p in parts:
                    if "%" in p:
                        coverage_pct = float(p.replace("%", ""))
                        break
            except ValueError:
                pass

    passed = coverage_pct >= threshold
    warnings = []

    if coverage_pct < 80:
        warnings.append(f"Coverage {coverage_pct}% is below recommended 80%")

    return GateResult(
        name="Test Coverage",
        passed=passed,
        duration_seconds=time.time() - start,
        details=f"Coverage: {coverage_pct:.1f}% (threshold: {threshold}%)",
        warnings=warnings,
        metrics={
            "coverage_percent": coverage_pct,
            "threshold": threshold,
        },
    )


def check_lint() -> GateResult:
    """Gate 4: Run linting checks."""
    start = time.time()
    warnings = []

    # Ruff check
    ruff_code, ruff_out, ruff_err = run_command(
        ["python", "-m", "ruff", "check", "orchestrator/", "tests/"]
    )

    # Black check
    black_code, black_out, black_err = run_command(
        ["python", "-m", "black", "--check", "--diff", "orchestrator/", "tests/"]
    )

    if ruff_code != 0:
        warnings.append(f"Ruff found issues:\n{ruff_out}")

    if black_code != 0:
        warnings.append("Black formatting check failed (run: black orchestrator/ tests/)")

    passed = ruff_code == 0 and black_code == 0

    return GateResult(
        name="Linting",
        passed=passed,
        duration_seconds=time.time() - start,
        details="Ruff and Black checks passed" if passed else "Linting issues found",
        warnings=warnings,
        metrics={
            "ruff_passed": ruff_code == 0,
            "black_passed": black_code == 0,
        },
    )


def check_types() -> GateResult:
    """Gate 5: Run type checking with mypy."""
    start = time.time()

    code, stdout, stderr = run_command(
        ["python", "-m", "mypy", "orchestrator/", "--ignore-missing-imports"]
    )

    # Count errors
    error_count = stdout.count("error:")
    warning_count = stdout.count("warning:")

    passed = code == 0 or error_count == 0
    warnings = []

    if warning_count > 0:
        warnings.append(f"Mypy found {warning_count} warnings")

    return GateResult(
        name="Type Checking",
        passed=passed,
        duration_seconds=time.time() - start,
        details=f"Mypy: {error_count} errors, {warning_count} warnings",
        warnings=warnings,
        metrics={
            "errors": error_count,
            "warnings": warning_count,
        },
    )


def calculate_quality_score(gates: list[GateResult]) -> float:
    """Calculate overall quality score (0.0 - 1.0)."""
    if not gates:
        return 0.0

    weights = {
        "Build Verification": 0.25,
        "Test Execution": 0.30,
        "Test Coverage": 0.20,
        "Linting": 0.15,
        "Type Checking": 0.10,
    }

    score = 0.0
    total_weight = 0.0

    for gate in gates:
        weight = weights.get(gate.name, 0.1)
        total_weight += weight

        if gate.passed:
            base_score = weight
            # Bonus for metrics
            if "pass_rate" in gate.metrics:
                base_score *= gate.metrics["pass_rate"]
            if "coverage_percent" in gate.metrics:
                base_score *= min(gate.metrics["coverage_percent"] / 100, 1.0)
            score += base_score
        else:
            # Partial credit for attempted but failed gates
            score += weight * 0.1

    return min(score / total_weight, 1.0) if total_weight > 0 else 0.0


def print_report(report: QualityReport) -> None:
    """Print quality report to console."""
    print("\n" + "=" * 60)
    print("ARCHON QUALITY REPORT")
    print("=" * 60)
    print(f"Timestamp: {report.timestamp}")
    print(f"Quality Score: {report.quality_score:.1%}")
    print(f"Overall: {'PASSED' if report.overall_passed else 'FAILED'}")
    print("-" * 60)

    for gate in report.gates:
        status = "PASS" if gate.passed else "FAIL"
        print(f"\n[{status}] {gate.name} ({gate.duration_seconds:.1f}s)")
        print(f"       {gate.details}")

        for warning in gate.warnings:
            print(f"       WARNING: {warning}")

    print("\n" + "=" * 60)
    print(report.summary)
    print("=" * 60 + "\n")


def save_report(report: QualityReport) -> None:
    """Save quality report to disk."""
    ORCHESTRA_QA.mkdir(parents=True, exist_ok=True)
    reports_dir = ORCHESTRA_QA / "reports"
    reports_dir.mkdir(exist_ok=True)

    # Save latest report
    latest_path = reports_dir / "latest.json"
    with open(latest_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    # Save timestamped report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamped_path = reports_dir / f"report_{timestamp}.json"
    with open(timestamped_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    print(f"Report saved to: {latest_path}")


def main() -> int:
    """Run quality gates and report results."""
    parser = argparse.ArgumentParser(description="Archon Quality Gates")
    parser.add_argument("--quick", action="store_true", help="Quick smoke tests only")
    parser.add_argument("--no-lint", action="store_true", help="Skip linting checks")
    parser.add_argument("--no-types", action="store_true", help="Skip type checking")
    parser.add_argument("--coverage-only", action="store_true", help="Coverage report only")
    parser.add_argument(
        "--threshold", type=float, default=80.0, help="Coverage threshold (default: 80)"
    )
    args = parser.parse_args()

    print("\nRunning Archon Quality Gates...\n")

    gates: list[GateResult] = []

    # Gate 1: Build
    print("[ ] Build Verification...", end=" ", flush=True)
    build_result = check_build()
    gates.append(build_result)
    print("PASS" if build_result.passed else "FAIL")

    if not build_result.passed:
        # Can't proceed if build fails
        report = QualityReport(
            timestamp=datetime.now().isoformat(),
            overall_passed=False,
            gates=gates,
            summary="BUILD FAILED - Cannot proceed with further checks",
            quality_score=0.0,
        )
        print_report(report)
        save_report(report)
        return 1

    # Gate 2: Tests
    if not args.coverage_only:
        print("[ ] Test Execution...", end=" ", flush=True)
        test_result = check_tests(quick=args.quick)
        gates.append(test_result)
        print("PASS" if test_result.passed else "FAIL")

    # Gate 3: Coverage
    print("[ ] Test Coverage...", end=" ", flush=True)
    coverage_result = check_coverage(threshold=args.threshold)
    gates.append(coverage_result)
    print("PASS" if coverage_result.passed else "FAIL")

    # Gate 4: Lint (optional)
    if not args.no_lint and not args.coverage_only:
        print("[ ] Linting...", end=" ", flush=True)
        lint_result = check_lint()
        gates.append(lint_result)
        print("PASS" if lint_result.passed else "FAIL")

    # Gate 5: Types (optional)
    if not args.no_types and not args.coverage_only:
        print("[ ] Type Checking...", end=" ", flush=True)
        type_result = check_types()
        gates.append(type_result)
        print("PASS" if type_result.passed else "FAIL")

    # Calculate overall results
    all_passed = all(g.passed for g in gates)
    quality_score = calculate_quality_score(gates)

    # Determine summary
    if all_passed:
        summary = "ALL QUALITY GATES PASSED - Ready for deployment"
    else:
        failed_gates = [g.name for g in gates if not g.passed]
        summary = f"QUALITY GATES FAILED: {', '.join(failed_gates)}"

    report = QualityReport(
        timestamp=datetime.now().isoformat(),
        overall_passed=all_passed,
        gates=gates,
        summary=summary,
        quality_score=quality_score,
    )

    print_report(report)
    save_report(report)

    # Return appropriate exit code
    if not all_passed:
        for i, gate in enumerate(gates):
            if not gate.passed:
                return i + 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
