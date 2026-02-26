"""
Tests for the Living Contract Negotiation System.

Contracts in the organic architecture are living documents:
- Proposed: T1 suggests an interface (NEGOTIATING status)
- Counter-proposed: T2 suggests modifications
- Mediated: Manager helps resolve differences (resolution)
- Agreed: Both parties accept
- Implemented: T2 builds it
- Verified: T5 confirms it works

Contracts enable parallel work by documenting expectations.
"""

import pytest

from orchestrator.config import Config
from orchestrator.contract_manager import ContractManager, ContractStatus


class TestContractProposal:
    """Test creating and proposing contracts."""

    def test_propose_contract(self, contract_manager: ContractManager):
        """Can propose a new contract."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="UserDataProvider",
            contract_type="interface",
            content="I need a UserDataProvider with getCurrentUser method",
            code_block="""
protocol UserDataProvider {
    func getCurrentUser() async -> User
}
""",
        )

        assert contract is not None
        assert contract.name == "UserDataProvider"
        assert contract.proposer == "t1"
        assert contract.status == ContractStatus.NEGOTIATING

    def test_contract_initial_status_is_negotiating(self, contract_manager: ContractManager):
        """New contracts should have 'negotiating' status."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="TestContract",
            contract_type="interface",
            content="Test proposal",
        )

        assert contract.status == ContractStatus.NEGOTIATING

    def test_cannot_create_duplicate_contract(self, contract_manager: ContractManager):
        """Cannot create a contract with an existing name."""
        contract_manager.propose_contract(
            from_terminal="t1",
            name="UniqueContract",
            contract_type="interface",
            content="First proposal",
        )

        with pytest.raises(ValueError) as exc_info:
            contract_manager.propose_contract(
                from_terminal="t2",
                name="UniqueContract",
                contract_type="api",
                content="Duplicate proposal",
            )

        assert "already exists" in str(exc_info.value)

    def test_contract_saved_to_disk(self, contract_manager: ContractManager, config: Config):
        """Contracts should be persisted to disk."""
        _ = config
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="PersistentContract",
            contract_type="interface",
            content="Test persistence",
        )

        # Check file exists
        contract_path = contract_manager._get_contract_path(contract.id)
        assert contract_path.exists()


class TestContractResponse:
    """Test responding to contracts (counter-offers)."""

    def test_respond_to_contract(self, contract_manager: ContractManager):
        """Can respond to an existing contract."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="ResponseTest",
            contract_type="interface",
            content="Initial proposal",
        )

        updated = contract_manager.respond_to_contract(
            terminal="t2",
            contract_id=contract.id,
            response="I can implement this as an Observable class",
            action="response",
        )

        assert len(updated.history) == 2
        assert updated.history[1].terminal == "t2"
        assert updated.history[1].action == "response"

    def test_counter_proposal(self, contract_manager: ContractManager):
        """Can counter-propose with modifications."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="CounterTest",
            contract_type="interface",
            content="Initial proposal",
        )

        updated = contract_manager.respond_to_contract(
            terminal="t2",
            contract_id=contract.id,
            response="I suggest using Observable instead of protocol",
            code_block="""
@Observable
class UserStore {
    var currentUser: User?
}
""",
            action="counter",
        )

        assert updated.history[1].action == "counter"
        assert updated.history[1].code_block is not None

    def test_respond_nonexistent_contract_raises(self, contract_manager: ContractManager):
        """Responding to a non-existent contract should raise."""
        with pytest.raises(ValueError) as exc_info:
            contract_manager.respond_to_contract(
                terminal="t2",
                contract_id="nonexistent_id",
                response="This should fail",
            )

        assert "not found" in str(exc_info.value)


class TestContractMediation:
    """Test contract mediation when parties disagree."""

    def test_resolve_contract(self, contract_manager: ContractManager):
        """Manager can resolve a contract negotiation."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="MediationTest",
            contract_type="interface",
            content="Initial proposal",
        )

        contract_manager.respond_to_contract(
            terminal="t2",
            contract_id=contract.id,
            response="I disagree with this approach",
            action="counter",
        )

        resolved = contract_manager.resolve_contract(
            terminal="t4",
            contract_id=contract.id,
            resolution="After reviewing both sides, let's use Observable pattern",
            code_block="""
@Observable
class UserStore {
    var currentUser: User?
}
""",
        )

        assert resolved.status == ContractStatus.AGREED
        assert resolved.agreed_at is not None

    def test_dispute_contract(self, contract_manager: ContractManager):
        """Can flag a contract as disputed."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="DisputeTest",
            contract_type="interface",
            content="Proposal",
        )

        disputed = contract_manager.respond_to_contract(
            terminal="t2",
            contract_id=contract.id,
            response="This breaks our architecture",
            action="dispute",
        )

        assert disputed.status == ContractStatus.DISPUTED


class TestContractImplementation:
    """Test contract implementation tracking."""

    def test_implement_contract(self, contract_manager: ContractManager):
        """Can mark a contract as implemented."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="ImplTest",
            contract_type="interface",
            content="Need UserService",
        )

        # Agree first
        contract_manager.respond_to_contract(
            terminal="t2",
            contract_id=contract.id,
            response="I agree to implement this",
            action="agree",
        )

        # Implement
        implemented = contract_manager.implement_contract(
            terminal="t2",
            contract_id=contract.id,
            details="Implemented as UserService class",
            file_path="Sources/UserService.swift",
            quality=0.85,
        )

        assert implemented.status == ContractStatus.IMPLEMENTED
        assert implemented.implemented_at is not None
        assert implemented.implementer == "t2"

    def test_list_pending_contracts(self, contract_manager: ContractManager):
        """Can list contracts that need action."""
        # Create contracts in different states
        c1 = contract_manager.propose_contract(
            from_terminal="t1",
            name="Pending1",
            contract_type="interface",
            content="Needs response",
        )

        contract_manager.propose_contract(
            from_terminal="t1",
            name="Pending2",
            contract_type="api",
            content="Also needs response",
        )

        # Implement one
        contract_manager.implement_contract(
            terminal="t2",
            contract_id=c1.id,
            details="Done",
            quality=0.8,
        )

        pending = contract_manager.list_pending_contracts()

        # c2 should still be pending, c1 is implemented
        assert any(c.name == "Pending2" for c in pending)


class TestContractVerification:
    """Test contract verification by T5."""

    def test_verify_contract_success(self, contract_manager: ContractManager):
        """Can verify a contract implementation matches."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="VerifyTest",
            contract_type="interface",
            content="Need verified",
        )

        contract_manager.implement_contract(
            terminal="t2",
            contract_id=contract.id,
            details="Implemented",
            quality=0.8,
        )

        verified = contract_manager.verify_contract(
            terminal="t5",
            contract_id=contract.id,
            verified=True,
            notes="All methods present and signatures match",
            quality=0.9,
        )

        assert verified.status == ContractStatus.VERIFIED
        assert verified.verified_at is not None

    def test_verify_contract_failure(self, contract_manager: ContractManager):
        """Verification failure marks contract as disputed."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="FailVerify",
            contract_type="interface",
            content="Will fail verification",
        )

        contract_manager.implement_contract(
            terminal="t2",
            contract_id=contract.id,
            details="Implemented",
            quality=0.7,
        )

        verified = contract_manager.verify_contract(
            terminal="t5",
            contract_id=contract.id,
            verified=False,
            notes="Method signature mismatch on getUserData()",
        )

        assert verified.status == ContractStatus.DISPUTED


class TestNegotiationHistoryTracking:
    """Test tracking negotiation history."""

    def test_contract_timestamps_updated(self, contract_manager: ContractManager):
        """Contract timestamps should be updated on changes."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="TimestampTest",
            contract_type="interface",
            content="Test timestamps",
        )

        original_created = contract.created_at
        original_updated = contract.updated_at

        # Wait and update
        import time

        time.sleep(0.01)

        updated = contract_manager.respond_to_contract(
            terminal="t2",
            contract_id=contract.id,
            response="Response here",
        )

        assert updated.created_at == original_created
        assert updated.updated_at != original_updated

    def test_contract_to_markdown(self, contract_manager: ContractManager):
        """Contracts can be formatted as markdown."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="MarkdownTest",
            contract_type="interface",
            content="Test markdown output",
            code_block="struct User { let id: UUID }",
        )

        md = contract.to_markdown()

        assert "# Contract: MarkdownTest" in md
        assert "Negotiating" in md
        assert "T1" in md


class TestContractQueries:
    """Test querying and filtering contracts."""

    def test_list_all_contracts(self, contract_manager: ContractManager):
        """Can list all contracts."""
        contract_manager.propose_contract(
            from_terminal="t1",
            name="C1",
            contract_type="interface",
            content="First",
        )
        contract_manager.propose_contract(
            from_terminal="t2",
            name="C2",
            contract_type="api",
            content="Second",
        )

        all_contracts = contract_manager.list_contracts()

        assert len(all_contracts) == 2

    def test_list_contracts_by_status(self, contract_manager: ContractManager):
        """Can filter contracts by status."""
        c1 = contract_manager.propose_contract(
            from_terminal="t1",
            name="StatusTest1",
            contract_type="interface",
            content="First",
        )
        contract_manager.propose_contract(
            from_terminal="t1",
            name="StatusTest2",
            contract_type="interface",
            content="Second",
        )

        contract_manager.implement_contract(
            terminal="t2",
            contract_id=c1.id,
            details="Done",
            quality=0.8,
        )

        implemented = contract_manager.list_contracts(status=ContractStatus.IMPLEMENTED)
        negotiating = contract_manager.list_contracts(status=ContractStatus.NEGOTIATING)

        assert len(implemented) == 1
        assert len(negotiating) == 1

    def test_get_contract_by_id(self, contract_manager: ContractManager):
        """Can retrieve a specific contract by ID."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="SpecificContract",
            contract_type="interface",
            content="Specific test",
        )

        fetched = contract_manager.get_contract(contract.id)

        assert fetched is not None
        assert fetched.id == contract.id

    def test_get_contract_by_name(self, contract_manager: ContractManager):
        """Can retrieve a contract by name."""
        contract_manager.propose_contract(
            from_terminal="t1",
            name="NamedContract",
            contract_type="interface",
            content="Test",
        )

        fetched = contract_manager.get_contract_by_name("NamedContract")

        assert fetched is not None
        assert fetched.name == "NamedContract"

    def test_get_nonexistent_contract_returns_none(self, contract_manager: ContractManager):
        """Getting a non-existent contract returns None."""
        contract = contract_manager.get_contract("does_not_exist_12345")
        assert contract is None

    def test_get_contracts_for_terminal(self, contract_manager: ContractManager):
        """Can get contracts for a specific terminal."""
        contract_manager.propose_contract(
            from_terminal="t1",
            name="T1Contract",
            contract_type="interface",
            content="By T1",
        )
        contract_manager.propose_contract(
            from_terminal="t2",
            name="T2Contract",
            contract_type="api",
            content="By T2",
        )

        t1_contracts = contract_manager.get_contracts_for_terminal("t1", role="proposer")

        assert len(t1_contracts) == 1
        assert t1_contracts[0].proposer == "t1"


class TestContractSummary:
    """Test contract summary generation."""

    def test_empty_summary(self, contract_manager: ContractManager):
        """Empty contract summary when no contracts."""
        summary = contract_manager.get_contract_summary()

        assert "No contracts defined" in summary

    def test_summary_with_contracts(self, contract_manager: ContractManager):
        """Summary includes all contracts grouped by status."""
        c1 = contract_manager.propose_contract(
            from_terminal="t1",
            name="SummaryTest1",
            contract_type="interface",
            content="First",
        )
        contract_manager.propose_contract(
            from_terminal="t1",
            name="SummaryTest2",
            contract_type="api",
            content="Second",
        )

        contract_manager.implement_contract(
            terminal="t2",
            contract_id=c1.id,
            details="Done",
            quality=0.8,
        )

        summary = contract_manager.get_contract_summary()

        assert "Total:" in summary
        assert "Negotiating" in summary or "Implemented" in summary


class TestContractCleanup:
    """Test contract cleanup operations."""

    def test_delete_contract(self, contract_manager: ContractManager):
        """Can delete a specific contract."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="ToDelete",
            contract_type="interface",
            content="Delete me",
        )

        deleted = contract_manager.delete_contract(contract.id)

        assert deleted is True
        assert contract_manager.get_contract(contract.id) is None

    def test_delete_nonexistent_contract(self, contract_manager: ContractManager):
        """Deleting non-existent contract returns False."""
        deleted = contract_manager.delete_contract("does_not_exist_12345")
        assert deleted is False

    def test_clear_all_contracts(self, contract_manager: ContractManager):
        """Can clear all contracts."""
        contract_manager.propose_contract(
            from_terminal="t1",
            name="Clear1",
            contract_type="interface",
            content="First",
        )
        contract_manager.propose_contract(
            from_terminal="t2",
            name="Clear2",
            contract_type="api",
            content="Second",
        )

        contract_manager.clear_contracts()

        all_contracts = contract_manager.list_contracts()
        assert len(all_contracts) == 0

    def test_deprecate_contract(self, contract_manager: ContractManager):
        """Can mark a contract as deprecated."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="Deprecate",
            contract_type="interface",
            content="Will be deprecated",
        )

        deprecated = contract_manager.deprecate_contract(
            contract.id,
            reason="No longer needed - replaced by NewContract",
        )

        assert deprecated is not None
        assert deprecated.status == ContractStatus.DEPRECATED


class TestContractPersistence:
    """Test contract serialization/deserialization."""

    def test_contract_persists_and_loads(self, contract_manager: ContractManager):
        """Contracts persist to disk and can be loaded."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="PersistTest",
            contract_type="data_model",
            content="Test persistence with full cycle",
            tags=["user", "profile"],
        )

        # Add some history
        contract_manager.respond_to_contract(
            terminal="t2",
            contract_id=contract.id,
            response="I can implement this",
            action="agree",
        )

        # Load it back
        loaded = contract_manager.get_contract(contract.id)

        assert loaded is not None
        assert loaded.name == "PersistTest"
        assert len(loaded.history) >= 2

    def test_contract_history_preserved(self, contract_manager: ContractManager):
        """Contract negotiation history is preserved."""
        contract = contract_manager.propose_contract(
            from_terminal="t1",
            name="HistoryTest",
            contract_type="interface",
            content="Initial proposal",
        )

        contract_manager.respond_to_contract(
            terminal="t2",
            contract_id=contract.id,
            response="Counter proposal",
            action="counter",
        )

        contract_manager.resolve_contract(
            terminal="t4",
            contract_id=contract.id,
            resolution="Final resolution",
        )

        loaded = contract_manager.get_contract(contract.id)

        assert loaded is not None
        assert len(loaded.history) == 3
        assert loaded.history[0].action == "proposal"
        assert loaded.history[1].action == "counter"
        assert loaded.history[2].action == "resolution"
