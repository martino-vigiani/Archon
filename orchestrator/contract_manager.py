"""
Contract Manager for interface contracts between terminals.

Manages contracts (interface definitions) between T1 (UI) and T2 (backend),
enabling parallel development where T1 builds UI with mock data while
T2 implements the real APIs that match T1's expectations.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from .config import Config, TerminalID


ContractStatus = Literal["proposed", "implemented", "verified"]


@dataclass
class Contract:
    """An interface contract between terminals."""

    name: str
    defined_by: TerminalID
    status: ContractStatus
    definition: dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    implemented_by: TerminalID | None = None
    notes: str = ""

    def to_dict(self) -> dict:
        """Convert contract to dictionary."""
        return {
            "name": self.name,
            "defined_by": self.defined_by,
            "status": self.status,
            "definition": self.definition,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "implemented_by": self.implemented_by,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Contract":
        """Create contract from dictionary."""
        return cls(
            name=data["name"],
            defined_by=data["defined_by"],
            status=data["status"],
            definition=data["definition"],
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            implemented_by=data.get("implemented_by"),
            notes=data.get("notes", ""),
        )

    def to_markdown(self) -> str:
        """Format contract as markdown."""
        status_emoji = {
            "proposed": "📝",
            "implemented": "✅",
            "verified": "🎯",
        }

        emoji = status_emoji.get(self.status, "❓")

        md = f"""# Contract: {self.name}

**Status:** {emoji} {self.status.upper()}
**Defined by:** {self.defined_by.upper()}
**Created:** {self.created_at}
**Updated:** {self.updated_at}
"""

        if self.implemented_by:
            md += f"**Implemented by:** {self.implemented_by.upper()}\n"

        md += "\n## Definition\n\n"
        md += "```json\n"
        md += json.dumps(self.definition, indent=2)
        md += "\n```\n"

        if self.notes:
            md += f"\n## Notes\n\n{self.notes}\n"

        return md


class ContractManager:
    """
    Manages interface contracts between terminals.

    The ContractManager enables parallel development by allowing terminals
    to define expectations of each other without blocking. Typical flow:

    1. T1 creates UI and defines a contract: "I need UserData with id, name, email"
    2. T1 builds UI using mock data matching the contract
    3. T2 reads the contract and implements the matching API
    4. T2 marks contract as "implemented"
    5. T5 (QA) verifies the contract matches and marks as "verified"

    This allows T1 and T2 to work in parallel without waiting for each other.
    """

    def __init__(self, config: Config):
        """
        Initialize the ContractManager.

        Args:
            config: Orchestrator configuration
        """
        self.config = config
        self._ensure_dirs()

    @property
    def contracts_dir(self) -> Path:
        """Get the contracts directory."""
        return self.config.orchestra_dir / "contracts"

    def _ensure_dirs(self) -> None:
        """Create contracts directory if it doesn't exist."""
        self.contracts_dir.mkdir(parents=True, exist_ok=True)

    def _get_contract_path(self, name: str) -> Path:
        """Get the path to a contract file."""
        # Sanitize name for filesystem
        safe_name = name.replace("/", "_").replace(" ", "_").lower()
        return self.contracts_dir / f"{safe_name}.json"

    def create_contract(
        self,
        name: str,
        defined_by: TerminalID,
        definition: dict[str, Any],
        notes: str = "",
    ) -> Contract:
        """
        Create a new interface contract.

        Args:
            name: Contract name (e.g., "UserDisplayData", "WeatherAPI")
            defined_by: Terminal that defined this contract
            definition: Contract definition (structure, fields, types, etc.)
            notes: Additional notes or context

        Returns:
            The created Contract object

        Raises:
            ValueError: If contract with this name already exists
        """
        contract_path = self._get_contract_path(name)

        if contract_path.exists():
            raise ValueError(f"Contract '{name}' already exists. Use update_contract to modify it.")

        contract = Contract(
            name=name,
            defined_by=defined_by,
            status="proposed",
            definition=definition,
            notes=notes,
        )

        contract_path.write_text(json.dumps(contract.to_dict(), indent=2))

        # Also save markdown version for easy reading
        md_path = contract_path.with_suffix(".md")
        md_path.write_text(contract.to_markdown())

        return contract

    def update_contract_status(
        self,
        name: str,
        status: ContractStatus,
        implementer: TerminalID | None = None,
        notes: str | None = None,
    ) -> Contract:
        """
        Update the status of a contract.

        Args:
            name: Contract name
            status: New status
            implementer: Terminal that implemented this (if status is implemented/verified)
            notes: Additional notes to append

        Returns:
            The updated Contract object

        Raises:
            ValueError: If contract doesn't exist
        """
        contract = self.get_contract(name)

        if not contract:
            raise ValueError(f"Contract '{name}' does not exist")

        contract.status = status
        contract.updated_at = datetime.now().isoformat()

        if implementer:
            contract.implemented_by = implementer

        if notes:
            if contract.notes:
                contract.notes += f"\n\n**Update ({datetime.now().isoformat()}):** {notes}"
            else:
                contract.notes = notes

        # Save updated contract
        contract_path = self._get_contract_path(name)
        contract_path.write_text(json.dumps(contract.to_dict(), indent=2))

        # Update markdown
        md_path = contract_path.with_suffix(".md")
        md_path.write_text(contract.to_markdown())

        return contract

    def get_contract(self, name: str) -> Contract | None:
        """
        Get a contract by name.

        Args:
            name: Contract name

        Returns:
            Contract object if exists, None otherwise
        """
        contract_path = self._get_contract_path(name)

        if not contract_path.exists():
            return None

        try:
            data = json.loads(contract_path.read_text())
            return Contract.from_dict(data)
        except (json.JSONDecodeError, KeyError, IOError) as e:
            print(f"[ContractManager] Error reading contract '{name}': {e}")
            return None

    def list_contracts(self, status: ContractStatus | None = None) -> list[Contract]:
        """
        List all contracts, optionally filtered by status.

        Args:
            status: Filter by status (proposed, implemented, verified). If None, returns all.

        Returns:
            List of Contract objects
        """
        contracts = []

        if not self.contracts_dir.exists():
            return contracts

        for contract_file in self.contracts_dir.glob("*.json"):
            try:
                data = json.loads(contract_file.read_text())
                contract = Contract.from_dict(data)

                if status is None or contract.status == status:
                    contracts.append(contract)

            except (json.JSONDecodeError, KeyError, IOError) as e:
                print(f"[ContractManager] Error reading {contract_file}: {e}")
                continue

        # Sort by created_at
        contracts.sort(key=lambda c: c.created_at)

        return contracts

    def list_pending_contracts(self) -> list[Contract]:
        """
        List contracts that are not yet implemented.

        Returns:
            List of contracts with status "proposed"
        """
        return self.list_contracts(status="proposed")

    def verify_contract(
        self,
        name: str,
        implementation_matches: bool,
        verifier: TerminalID = "t5",
        notes: str = "",
    ) -> Contract:
        """
        Verify that a contract implementation matches its definition.

        Args:
            name: Contract name
            implementation_matches: Whether implementation matches the contract
            verifier: Terminal doing the verification (usually t5)
            notes: Verification notes or issues found

        Returns:
            The updated Contract object

        Raises:
            ValueError: If contract doesn't exist or not yet implemented
        """
        contract = self.get_contract(name)

        if not contract:
            raise ValueError(f"Contract '{name}' does not exist")

        if contract.status == "proposed":
            raise ValueError(f"Contract '{name}' is not yet implemented, cannot verify")

        if implementation_matches:
            status = "verified"
            verification_note = f"Verified by {verifier}: Implementation matches contract"
        else:
            status = "implemented"  # Keep as implemented but note issues
            verification_note = f"Verified by {verifier}: Issues found - {notes}"

        if notes:
            verification_note = f"{verification_note}\n{notes}"

        return self.update_contract_status(
            name=name,
            status=status,  # type: ignore
            notes=verification_note,
        )

    def get_contract_summary(self) -> str:
        """
        Get a human-readable summary of all contracts.

        Returns:
            Formatted string with contract overview
        """
        contracts = self.list_contracts()

        if not contracts:
            return "# Contract Summary\n\nNo contracts defined yet."

        lines = ["# Contract Summary\n"]

        # Group by status
        by_status: dict[str, list[Contract]] = {
            "proposed": [],
            "implemented": [],
            "verified": [],
        }

        for contract in contracts:
            by_status[contract.status].append(contract)

        # Summary stats
        lines.append(f"**Total:** {len(contracts)} contracts")
        lines.append(f"**Proposed:** {len(by_status['proposed'])}")
        lines.append(f"**Implemented:** {len(by_status['implemented'])}")
        lines.append(f"**Verified:** {len(by_status['verified'])}\n")

        # List by status
        for status, emoji in [("proposed", "📝"), ("implemented", "✅"), ("verified", "🎯")]:
            status_contracts = by_status[status]

            if status_contracts:
                lines.append(f"\n## {emoji} {status.upper()}\n")

                for contract in status_contracts:
                    implementer = ""
                    if contract.implemented_by:
                        implementer = f" (by {contract.implemented_by.upper()})"

                    lines.append(
                        f"- **{contract.name}** - defined by {contract.defined_by.upper()}{implementer}"
                    )

                    # Show a brief snippet of the definition
                    if isinstance(contract.definition, dict):
                        if "fields" in contract.definition:
                            fields = contract.definition["fields"]
                            if isinstance(fields, list) and len(fields) > 0:
                                field_names = ", ".join(str(f) for f in fields[:3])
                                if len(fields) > 3:
                                    field_names += f" (+{len(fields) - 3} more)"
                                lines.append(f"  Fields: {field_names}")

        return "\n".join(lines)

    def get_contracts_for_terminal(
        self,
        terminal_id: TerminalID,
        role: Literal["defined", "implementing"] = "implementing",
    ) -> list[Contract]:
        """
        Get contracts relevant to a specific terminal.

        Args:
            terminal_id: Terminal identifier
            role: "defined" for contracts this terminal defined,
                  "implementing" for contracts this terminal should implement

        Returns:
            List of relevant contracts
        """
        all_contracts = self.list_contracts()

        if role == "defined":
            return [c for c in all_contracts if c.defined_by == terminal_id]

        # For implementing, return pending contracts defined by other terminals
        # that this terminal should implement (typically T1 -> T2 or T2 -> T1)
        relevant = []

        for contract in all_contracts:
            # Skip contracts this terminal defined
            if contract.defined_by == terminal_id:
                continue

            # Include pending contracts
            if contract.status == "proposed":
                relevant.append(contract)

            # Include recently implemented contracts for context
            if contract.status == "implemented" and contract.implemented_by == terminal_id:
                relevant.append(contract)

        return relevant

    def clear_contracts(self) -> None:
        """Clear all contracts."""
        if self.contracts_dir.exists():
            for contract_file in self.contracts_dir.glob("*"):
                contract_file.unlink()

    def delete_contract(self, name: str) -> bool:
        """
        Delete a specific contract.

        Args:
            name: Contract name

        Returns:
            True if contract was deleted, False if it didn't exist
        """
        contract_path = self._get_contract_path(name)
        md_path = contract_path.with_suffix(".md")

        deleted = False

        if contract_path.exists():
            contract_path.unlink()
            deleted = True

        if md_path.exists():
            md_path.unlink()

        return deleted
