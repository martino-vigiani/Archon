#!/usr/bin/env python3
"""
Test Runner with Quality Reporting - Archon T5 Skeptic

This script runs tests and generates detailed quality reports for the
orchestrator. Designed to be used by T5 (The Skeptic) for continuous
verification.

Features:
- Runs pytest with configurable options
- Generates JSON quality reports
- Tracks test history over time
- Reports to .orchestra/qa for other terminals to monitor

Usage:
    python scripts/run_tests.py                  # Run all tests
    python scripts/run_tests.py --quick          # Quick smoke tests
    python scripts/run_tests.py --watch          # Watch mode
    python scripts/run_tests.py --report-only    # Just generate report
"""

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Literal

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
ORCHESTRA_QA = PROJECT_ROOT / ".orchestra" / "qa"
TESTS_DIR = ORCHESTRA_QA / "tests"
BUILDS_DIR = ORCHESTRA_QA / "builds"


@dataclass
class TestResult:
    """Individual test result."""

    name: str
    status: Literal["passed", "failed", "skipped", "error"]
    duration: float
    file: str
    line: int | None = None
    message: str | None = None


@dataclass
class TestSuiteReport:
    """Complete test suite report."""

    timestamp: str
    duration_seconds: float
    total: int
    passed: int
    failed: int
    skipped: int
    errors: int
    pass_rate: float
    tests: list[TestResult]
    summary: str
    quality_level: float  # 0.0 - 1.0 quality gradient

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "pass_rate": self.pass_rate,
            "quality_level": self.quality_level,
            "summary": self.summary,
            "tests": [asdict(t) for t in self.tests],
        }


def ensure_dirs() -> None:
    """Ensure QA directories exist."""
    TESTS_DIR.mkdir(parents=True, exist_ok=True)
    BUILDS_DIR.mkdir(parents=True, exist_ok=True)


def run_pytest(
    quick: bool = False,
    verbose: bool = True,
    markers: str | None = None,
) -> tuple[int, str, str, float]:
    """Run pytest and return exit code, stdout, stderr, duration."""
    cmd = ["python", "-m", "pytest", "tests/"]

    if quick:
        cmd.extend(["-x", "-q", "--tb=line", "-m", "smoke or not slow"])
    else:
        cmd.extend(["--tb=short"])

    if verbose:
        cmd.append("-v")

    if markers:
        cmd.extend(["-m", markers])

    # JSON output for parsing
    json_path = TESTS_DIR / "results.json"
    cmd.extend(
        [
            f"--json-report",
            f"--json-report-file={json_path}",
        ]
    )

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
        duration = time.time() - start
        return result.returncode, result.stdout, result.stderr, duration
    except subprocess.TimeoutExpired:
        return -1, "", "Test execution timed out", time.time() - start


def run_pytest_simple(quick: bool = False) -> tuple[int, str, str, float]:
    """Run pytest without json plugin (fallback)."""
    cmd = ["python", "-m", "pytest", "tests/"]

    if quick:
        cmd.extend(["-x", "-q", "--tb=line", "-m", "smoke or not slow"])
    else:
        cmd.extend(["--tb=short", "-v"])

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
        duration = time.time() - start
        return result.returncode, result.stdout, result.stderr, duration
    except subprocess.TimeoutExpired:
        return -1, "", "Test execution timed out", time.time() - start


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


def parse_pytest_output(stdout: str, stderr: str) -> tuple[int, int, int, int]:
    """Parse pytest output for test counts."""
    passed = 0
    failed = 0
    skipped = 0
    errors = 0

    # Strip ANSI codes for cleaner parsing
    clean_stdout = strip_ansi(stdout)
    clean_stderr = strip_ansi(stderr)

    # Look for the summary line like "213 passed" or "10 passed, 2 failed, 1 skipped"
    import re
    for line in clean_stdout.split("\n") + clean_stderr.split("\n"):
        # Match patterns like "213 passed" or "10 passed, 2 failed"
        passed_match = re.search(r'(\d+)\s+passed', line)
        failed_match = re.search(r'(\d+)\s+failed', line)
        skipped_match = re.search(r'(\d+)\s+skipped', line)
        error_match = re.search(r'(\d+)\s+error', line)

        if passed_match:
            passed = int(passed_match.group(1))
        if failed_match:
            failed = int(failed_match.group(1))
        if skipped_match:
            skipped = int(skipped_match.group(1))
        if error_match:
            errors = int(error_match.group(1))

    return passed, failed, skipped, errors


def calculate_quality_level(passed: int, failed: int, total: int) -> float:
    """
    Calculate quality level based on test results.

    Quality gradient (per Archon philosophy):
    - 0.0-0.2: Sketch/Concept (many failures)
    - 0.2-0.4: Draft (some tests pass)
    - 0.4-0.6: Working (most tests pass)
    - 0.6-0.8: Solid (few failures)
    - 0.8-0.9: Polished (all pass, good coverage)
    - 0.9-1.0: Excellent (all pass, comprehensive)
    """
    if total == 0:
        return 0.0

    pass_rate = passed / total

    # Base quality from pass rate
    if pass_rate == 1.0:
        quality = 0.9
    elif pass_rate >= 0.95:
        quality = 0.8
    elif pass_rate >= 0.85:
        quality = 0.7
    elif pass_rate >= 0.70:
        quality = 0.6
    elif pass_rate >= 0.50:
        quality = 0.4
    elif pass_rate >= 0.25:
        quality = 0.2
    else:
        quality = 0.1

    # Bonus for having many tests
    if total >= 50:
        quality = min(quality + 0.05, 1.0)
    elif total >= 20:
        quality = min(quality + 0.02, 1.0)

    return round(quality, 2)


def generate_report(
    exit_code: int,
    stdout: str,
    stderr: str,
    duration: float,
) -> TestSuiteReport:
    """Generate a test suite report from pytest output."""
    passed, failed, skipped, errors = parse_pytest_output(stdout, stderr)
    total = passed + failed + skipped + errors

    if total == 0:
        # No tests found or parsing failed
        total = 1 if exit_code != 0 else 0
        failed = 1 if exit_code != 0 else 0

    pass_rate = passed / total if total > 0 else 0.0
    quality = calculate_quality_level(passed, failed, total)

    # Generate summary
    if exit_code == 0:
        summary = f"ALL TESTS PASSED ({passed} tests)"
    else:
        summary = f"TESTS FAILED: {failed} failures, {errors} errors out of {total} tests"

    return TestSuiteReport(
        timestamp=datetime.now().isoformat(),
        duration_seconds=round(duration, 2),
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        pass_rate=round(pass_rate, 4),
        quality_level=quality,
        summary=summary,
        tests=[],  # Individual tests would be parsed from JSON if available
    )


def save_report(report: TestSuiteReport) -> Path:
    """Save report to disk."""
    ensure_dirs()

    # Save latest
    latest_path = TESTS_DIR / "latest.json"
    with open(latest_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    # Save timestamped
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ts_path = TESTS_DIR / f"report_{ts}.json"
    with open(ts_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    return latest_path


def print_report(report: TestSuiteReport) -> None:
    """Print report to console."""
    status = "PASS" if report.failed == 0 and report.errors == 0 else "FAIL"

    print("\n" + "=" * 50)
    print(f"TEST REPORT - {status}")
    print("=" * 50)
    print(f"Timestamp: {report.timestamp}")
    print(f"Duration:  {report.duration_seconds:.1f}s")
    print(f"Quality:   {report.quality_level:.0%}")
    print("-" * 50)
    print(f"Total:     {report.total}")
    print(f"Passed:    {report.passed}")
    print(f"Failed:    {report.failed}")
    print(f"Skipped:   {report.skipped}")
    print(f"Errors:    {report.errors}")
    print(f"Pass Rate: {report.pass_rate:.1%}")
    print("-" * 50)
    print(f"Summary: {report.summary}")
    print("=" * 50 + "\n")


def update_heartbeat(report: TestSuiteReport) -> None:
    """Update T5 heartbeat with test status."""
    state_dir = PROJECT_ROOT / ".orchestra" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    heartbeat = {
        "terminal": "t5",
        "personality": "skeptic",
        "status": "verifying",
        "current_work": "Test monitoring",
        "build_status": "PASS" if report.failed == 0 else "FAIL",
        "tests_passing": report.passed,
        "tests_failing": report.failed,
        "quality": report.quality_level,
        "needs": [],
        "offers": ["Build verification", "Test coverage", "Quality gates"],
        "timestamp": datetime.now().isoformat(),
    }

    with open(state_dir / "t5_heartbeat.json", "w") as f:
        json.dump(heartbeat, f, indent=2)


def watch_mode(interval: int = 120) -> None:
    """Run tests continuously."""
    print(f"Starting watch mode (interval: {interval}s)")
    print("Press Ctrl+C to stop\n")

    try:
        while True:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Running tests...")

            exit_code, stdout, stderr, duration = run_pytest_simple(quick=True)
            report = generate_report(exit_code, stdout, stderr, duration)

            print_report(report)
            save_report(report)
            update_heartbeat(report)

            print(f"Next run in {interval} seconds...")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nWatch mode stopped.")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Archon Test Runner")
    parser.add_argument("--quick", action="store_true", help="Quick smoke tests")
    parser.add_argument("--watch", action="store_true", help="Watch mode")
    parser.add_argument("--interval", type=int, default=120, help="Watch interval (seconds)")
    parser.add_argument("--report-only", action="store_true", help="Generate report only")
    parser.add_argument("-m", "--markers", help="Pytest markers to filter tests")
    parser.add_argument("-q", "--quiet", action="store_true", help="Minimal output")
    args = parser.parse_args()

    ensure_dirs()

    if args.watch:
        watch_mode(interval=args.interval)
        return 0

    if args.report_only:
        # Load and display latest report
        latest = TESTS_DIR / "latest.json"
        if latest.exists():
            with open(latest) as f:
                data = json.load(f)
            print(json.dumps(data, indent=2))
        else:
            print("No report found. Run tests first.")
        return 0

    # Run tests
    print("Running tests...")
    exit_code, stdout, stderr, duration = run_pytest_simple(quick=args.quick)

    if not args.quiet:
        print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)

    # Generate and save report
    report = generate_report(exit_code, stdout, stderr, duration)
    report_path = save_report(report)

    if not args.quiet:
        print_report(report)

    # Update T5 heartbeat
    update_heartbeat(report)

    print(f"Report saved: {report_path}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
