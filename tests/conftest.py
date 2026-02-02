"""
Shared pytest fixtures for Archon 2.0 Organic Architecture tests.

Provides common setup for:
- Config objects
- Task queues with organic flow support
- Manager intelligence
- Contract manager
- Mock terminals and heartbeats
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.config import Config, TerminalConfig, TerminalID
from orchestrator.contract_manager import Contract, ContractManager, ContractStatus
from orchestrator.manager_intelligence import (
    ManagerIntelligence,
    TerminalHeartbeat,
)
from orchestrator.report_manager import Report, ReportManager
from orchestrator.task_queue import FlowState, Task, TaskPriority, TaskQueue, TaskStatus


# =============================================================================
# Base Fixtures
# =============================================================================


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def config(temp_dir: Path) -> Config:
    """Create a Config with temporary directories for testing."""
    config = Config(
        base_dir=temp_dir,
        orchestra_dir=temp_dir / ".orchestra",
        templates_dir=temp_dir / "templates",
        agents_dir=temp_dir / ".claude" / "agents",
        apps_dir=temp_dir / "Apps",
    )
    config.ensure_dirs()
    return config


@pytest.fixture
def task_queue(config: Config) -> TaskQueue:
    """Create a TaskQueue instance for testing."""
    return TaskQueue(config)


@pytest.fixture
def manager_intelligence(config: Config, task_queue: TaskQueue) -> ManagerIntelligence:
    """Create a ManagerIntelligence instance for testing."""
    return ManagerIntelligence(config, task_queue)


@pytest.fixture
def contract_manager(config: Config) -> ContractManager:
    """Create a ContractManager instance for testing."""
    return ContractManager(config)


@pytest.fixture
def report_manager(config: Config) -> ReportManager:
    """Create a ReportManager instance for testing."""
    return ReportManager(config)


# =============================================================================
# Task Fixtures
# =============================================================================


@pytest.fixture
def sample_task() -> Task:
    """Create a sample task with default values."""
    return Task(
        id="task_001",
        title="Build Login UI",
        description="Create the login screen with email and password fields",
        assigned_to="t1",
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
        phase=1,
        quality_level=0.0,
        flow_state=FlowState.FLOWING,
    )


@pytest.fixture
def sample_task_with_dependencies() -> Task:
    """Create a task that depends on other tasks."""
    return Task(
        id="task_002",
        title="Integrate Login with API",
        description="Connect login UI to authentication service",
        assigned_to="t1",
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
        dependencies=["task_001", "auth_service"],
        phase=2,
        quality_level=0.0,
        flow_state=FlowState.FLOWING,
    )


@pytest.fixture
def high_quality_task() -> Task:
    """Create a task with high quality level (near completion)."""
    return Task(
        id="task_003",
        title="User Profile View",
        description="Display user profile information",
        assigned_to="t1",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.MEDIUM,
        phase=1,
        quality_level=0.85,
        flow_state=FlowState.FLOURISHING,
    )


@pytest.fixture
def blocked_task() -> Task:
    """Create a blocked task."""
    return Task(
        id="task_004",
        title="Payment Integration",
        description="Integrate Stripe payment processing",
        assigned_to="t2",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.HIGH,
        phase=2,
        quality_level=0.3,
        flow_state=FlowState.BLOCKED,
        metadata={"blocked_reason": "Waiting for API keys"},
    )


# =============================================================================
# Heartbeat Fixtures
# =============================================================================


@pytest.fixture
def sample_heartbeat() -> TerminalHeartbeat:
    """Create a sample terminal heartbeat."""
    return TerminalHeartbeat(
        terminal_id="t1",
        timestamp=datetime.now().isoformat(),
        current_task_id="task_001",
        current_task_title="Build Login UI",
        progress_percent=50,
        files_being_edited=["LoginView.swift", "LoginViewModel.swift"],
        files_recently_created=["LoginView.swift"],
        is_blocked=False,
    )


@pytest.fixture
def blocked_heartbeat() -> TerminalHeartbeat:
    """Create a heartbeat for a blocked terminal."""
    return TerminalHeartbeat(
        terminal_id="t1",
        timestamp=datetime.now().isoformat(),
        current_task_id="task_002",
        current_task_title="Integrate Login with API",
        progress_percent=30,
        files_being_edited=["LoginView.swift"],
        is_blocked=True,
        blocker_reason="Waiting for UserService API from T2",
    )


@pytest.fixture
def stale_heartbeat() -> TerminalHeartbeat:
    """Create a stale/old heartbeat (simulating a stalled terminal)."""
    from datetime import timedelta
    old_time = datetime.now() - timedelta(seconds=300)
    return TerminalHeartbeat(
        terminal_id="t2",
        timestamp=old_time.isoformat(),
        current_task_id="task_003",
        current_task_title="Build UserService",
        progress_percent=40,
        is_blocked=False,
    )


@pytest.fixture
def all_heartbeats() -> dict[TerminalID, TerminalHeartbeat]:
    """Create heartbeats for all terminals."""
    now = datetime.now().isoformat()
    return {
        "t1": TerminalHeartbeat(
            terminal_id="t1",
            timestamp=now,
            current_task_id="task_001",
            current_task_title="Build Login UI",
            progress_percent=60,
            files_being_edited=["LoginView.swift"],
        ),
        "t2": TerminalHeartbeat(
            terminal_id="t2",
            timestamp=now,
            current_task_id="task_002",
            current_task_title="Build UserService",
            progress_percent=70,
            files_being_edited=["UserService.swift"],
        ),
        "t3": TerminalHeartbeat(
            terminal_id="t3",
            timestamp=now,
            current_task_id="task_003",
            current_task_title="Write README",
            progress_percent=80,
            files_being_edited=["README.md"],
        ),
        "t4": TerminalHeartbeat(
            terminal_id="t4",
            timestamp=now,
            current_task_id="task_004",
            current_task_title="Define MVP Scope",
            progress_percent=90,
        ),
        "t5": TerminalHeartbeat(
            terminal_id="t5",
            timestamp=now,
            current_task_id="task_005",
            current_task_title="Run Tests",
            progress_percent=50,
        ),
    }


# =============================================================================
# Contract Fixtures
# =============================================================================


@pytest.fixture
def sample_contract(contract_manager: ContractManager) -> Contract:
    """Create a sample contract in 'negotiating' state."""
    return contract_manager.propose_contract(
        from_terminal="t1",
        name="UserDataProvider",
        contract_type="interface",
        content="I need a UserDataProvider with getCurrentUser method",
        code_block="""
protocol UserDataProvider {
    func currentUser() async -> User
    func updateProfile(_ changes: ProfileChanges) async throws
}
""",
    )


@pytest.fixture
def implemented_contract(contract_manager: ContractManager) -> Contract:
    """Create a contract in 'implemented' state."""
    contract = contract_manager.propose_contract(
        from_terminal="t1",
        name="AuthService",
        contract_type="interface",
        content="Need AuthService for login/logout",
    )
    contract_manager.implement_contract(
        terminal="t2",
        contract_id=contract.id,
        details="Implemented as Observable class",
        quality=0.8,
    )
    return contract_manager.get_contract(contract.id)


@pytest.fixture
def verified_contract(contract_manager: ContractManager) -> Contract:
    """Create a verified contract."""
    contract = contract_manager.propose_contract(
        from_terminal="t1",
        name="HabitTracker",
        contract_type="interface",
        content="Need HabitTracker for habit management",
    )
    contract_manager.implement_contract(
        terminal="t2",
        contract_id=contract.id,
        details="Implemented HabitTracker",
        quality=0.85,
    )
    contract_manager.verify_contract(
        terminal="t5",
        contract_id=contract.id,
        verified=True,
        notes="All methods match contract",
    )
    return contract_manager.get_contract(contract.id)


# =============================================================================
# Report Fixtures
# =============================================================================


@pytest.fixture
def sample_report() -> Report:
    """Create a sample terminal report."""
    return Report(
        id="report_001",
        task_id="task_001",
        terminal_id="t1",
        summary="Created LoginView with email/password fields and validation",
        files_created=["LoginView.swift", "LoginViewModel.swift"],
        files_modified=[],
        components_created=["LoginView", "LoginViewModel"],
        dependencies_needed=[
            {"from": "t2", "what": "AuthService for login API"},
        ],
        provides_to_others=[
            {"to": "t2", "what": "LoginView ready for integration"},
            {"to": "all", "what": "Login UI pattern for reuse"},
        ],
        next_steps=["Integrate with AuthService when available"],
        blockers=[],
        success=True,
    )


# =============================================================================
# Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_claude_cli():
    """Mock the Claude CLI subprocess calls."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout='{"summary": "Task completed successfully", "success": true}',
            stderr="",
            returncode=0,
        )
        yield mock_run


@pytest.fixture
def mock_terminal_output():
    """Provide sample terminal output for parsing tests."""
    return """
## T1 Craftsman - Work Update

### Current Focus
Building the login screen with modern SwiftUI design

### Quality: 0.7
UI is functional, validation works, needs polish

### What I've Made
- LoginView.swift: Main login screen - Quality 0.7
- LoginViewModel.swift: Business logic - Quality 0.8

### What I Need
- From T2: AuthService API for actual login
- From T4: Brand colors confirmed

### Contracts
- Proposed: UserDataProvider - awaiting response

### Verification
- Compiles: YES
- Previews: YES
- Runnable: YES
"""


# =============================================================================
# Intervention Type Fixtures
# =============================================================================


@pytest.fixture
def intervention_types():
    """Provide all intervention type names for parametrized tests."""
    return ["AMPLIFY", "REDIRECT", "MEDIATE", "INJECT", "PRUNE"]


# =============================================================================
# Terminal Personality Fixtures
# =============================================================================


@pytest.fixture
def terminal_personalities():
    """Provide terminal personality mappings."""
    return {
        "t1": {"name": "Craftsman", "role": "UI/UX", "superpower": "making things beautiful"},
        "t2": {"name": "Architect", "role": "Features", "superpower": "building reliable systems"},
        "t3": {"name": "Narrator", "role": "Docs", "superpower": "explaining clearly"},
        "t4": {"name": "Strategist", "role": "Strategy", "superpower": "seeing the whole board"},
        "t5": {"name": "Skeptic", "role": "QA/Testing", "superpower": "finding flaws"},
    }
