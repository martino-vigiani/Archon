"""
Tests for the Dashboard API endpoints.

Verifies all REST endpoints return correct structure and handle edge cases:
- /api/status, /api/tasks, /api/terminals, /api/messages
- /api/terminal-output/{id}, /api/subagents, /api/orchestrator-log
- /api/project, /api/artifacts, /api/events
- POST /api/terminal-output/{id}
- Input validation (invalid terminal IDs, missing data)
"""

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.dashboard import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# =============================================================================
# GET Endpoints
# =============================================================================


class TestStatusEndpoint:
    """Test /api/status endpoint."""

    @pytest.mark.api
    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/status")
        assert response.status_code == 200

    @pytest.mark.api
    async def test_contains_required_fields(self, client: AsyncClient) -> None:
        response = await client.get("/api/status")
        data = response.json()
        assert "state" in data
        assert "timestamp" in data

    @pytest.mark.api
    async def test_contains_project_info(self, client: AsyncClient) -> None:
        response = await client.get("/api/status")
        data = response.json()
        assert "project" in data
        assert "name" in data["project"]


class TestTasksEndpoint:
    """Test /api/tasks endpoint."""

    @pytest.mark.api
    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/tasks")
        assert response.status_code == 200

    @pytest.mark.api
    async def test_contains_all_queues(self, client: AsyncClient) -> None:
        response = await client.get("/api/tasks")
        data = response.json()
        assert "pending" in data
        assert "in_progress" in data
        assert "completed" in data
        assert "failed" in data

    @pytest.mark.api
    async def test_queues_are_lists(self, client: AsyncClient) -> None:
        response = await client.get("/api/tasks")
        data = response.json()
        for key in ["pending", "in_progress", "completed", "failed"]:
            assert isinstance(data[key], list)


class TestTaskByIdEndpoint:
    """Test /api/tasks/{task_id} endpoint."""

    @pytest.mark.api
    async def test_nonexistent_task_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/tasks/nonexistent_task_xyz")
        assert response.status_code == 404


class TestTerminalsEndpoint:
    """Test /api/terminals endpoint."""

    @pytest.mark.api
    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/terminals")
        assert response.status_code == 200

    @pytest.mark.api
    async def test_contains_all_five_terminals(self, client: AsyncClient) -> None:
        response = await client.get("/api/terminals")
        data = response.json()
        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            assert tid in data

    @pytest.mark.api
    async def test_terminal_has_role(self, client: AsyncClient) -> None:
        response = await client.get("/api/terminals")
        data = response.json()
        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            assert "role" in data[tid]
            assert "description" in data[tid]


class TestMessagesEndpoint:
    """Test /api/messages endpoint."""

    @pytest.mark.api
    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/messages")
        assert response.status_code == 200

    @pytest.mark.api
    async def test_returns_dict(self, client: AsyncClient) -> None:
        response = await client.get("/api/messages")
        data = response.json()
        assert isinstance(data, dict)


class TestTerminalOutputEndpoint:
    """Test /api/terminal-output/{terminal_id} endpoint."""

    @pytest.mark.api
    async def test_valid_terminal_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/terminal-output/t1")
        assert response.status_code == 200

    @pytest.mark.api
    async def test_invalid_terminal_returns_400(self, client: AsyncClient) -> None:
        response = await client.get("/api/terminal-output/t99")
        assert response.status_code == 400

    @pytest.mark.api
    async def test_response_structure(self, client: AsyncClient) -> None:
        response = await client.get("/api/terminal-output/t1")
        data = response.json()
        assert "terminal_id" in data
        assert "output" in data
        assert data["terminal_id"] == "t1"

    @pytest.mark.api
    @pytest.mark.parametrize("terminal_id", ["t1", "t2", "t3", "t4", "t5"])
    async def test_all_valid_terminals(self, client: AsyncClient, terminal_id: str) -> None:
        response = await client.get(f"/api/terminal-output/{terminal_id}")
        assert response.status_code == 200


class TestSubagentsEndpoint:
    """Test /api/subagents endpoint."""

    @pytest.mark.api
    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/subagents")
        assert response.status_code == 200

    @pytest.mark.api
    async def test_contains_required_keys(self, client: AsyncClient) -> None:
        response = await client.get("/api/subagents")
        data = response.json()
        assert "invoked" in data
        assert "available" in data
        assert "total_invocations" in data

    @pytest.mark.api
    async def test_available_is_sorted_list(self, client: AsyncClient) -> None:
        response = await client.get("/api/subagents")
        data = response.json()
        available = data["available"]
        assert isinstance(available, list)
        assert available == sorted(available)


class TestOrchestratorLogEndpoint:
    """Test /api/orchestrator-log endpoint."""

    @pytest.mark.api
    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/orchestrator-log")
        assert response.status_code == 200

    @pytest.mark.api
    async def test_response_structure(self, client: AsyncClient) -> None:
        response = await client.get("/api/orchestrator-log")
        data = response.json()
        assert "entries" in data
        assert "count" in data
        assert isinstance(data["entries"], list)


class TestProjectEndpoint:
    """Test /api/project endpoint."""

    @pytest.mark.api
    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/project")
        assert response.status_code == 200

    @pytest.mark.api
    async def test_contains_name(self, client: AsyncClient) -> None:
        response = await client.get("/api/project")
        data = response.json()
        assert "name" in data


class TestArtifactsEndpoint:
    """Test /api/artifacts endpoint."""

    @pytest.mark.api
    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/artifacts")
        assert response.status_code == 200

    @pytest.mark.api
    async def test_returns_list(self, client: AsyncClient) -> None:
        response = await client.get("/api/artifacts")
        data = response.json()
        assert isinstance(data, list)


class TestEventsEndpoint:
    """Test /api/events endpoint."""

    @pytest.mark.api
    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/events")
        assert response.status_code == 200

    @pytest.mark.api
    async def test_returns_list(self, client: AsyncClient) -> None:
        response = await client.get("/api/events")
        data = response.json()
        assert isinstance(data, list)


# =============================================================================
# POST Endpoints
# =============================================================================


class TestPostTerminalOutput:
    """Test POST /api/terminal-output/{terminal_id}."""

    @pytest.mark.api
    async def test_save_output(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/terminal-output/t1",
            json={"content": "Test output from T1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "saved"
        assert data["terminal_id"] == "t1"

    @pytest.mark.api
    async def test_invalid_terminal_returns_400(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/terminal-output/invalid",
            json={"content": "test"},
        )
        assert response.status_code == 400

    @pytest.mark.api
    async def test_empty_content_accepted(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/terminal-output/t2",
            json={"content": ""},
        )
        assert response.status_code == 200


# =============================================================================
# Input Validation
# =============================================================================


class TestInputValidation:
    """Test input validation across endpoints."""

    @pytest.mark.api
    @pytest.mark.security
    async def test_terminal_id_injection_attempt(self, client: AsyncClient) -> None:
        """Path traversal in terminal_id should be rejected."""
        response = await client.get("/api/terminal-output/../../../etc/passwd")
        assert response.status_code in (400, 404, 422)

    @pytest.mark.api
    @pytest.mark.security
    async def test_terminal_id_special_chars(self, client: AsyncClient) -> None:
        """Special characters in terminal_id should be rejected."""
        response = await client.get("/api/terminal-output/t1%00")
        assert response.status_code in (400, 404, 422)

    @pytest.mark.api
    @pytest.mark.security
    async def test_large_max_lines_param(self, client: AsyncClient) -> None:
        """Very large max_lines should not crash the server."""
        response = await client.get("/api/terminal-output/t1?max_lines=999999")
        assert response.status_code == 200

    @pytest.mark.api
    @pytest.mark.security
    async def test_task_id_with_special_chars(self, client: AsyncClient) -> None:
        """Task ID with special chars should return 404, not crash."""
        response = await client.get("/api/tasks/<script>alert(1)</script>")
        assert response.status_code in (404, 422)
