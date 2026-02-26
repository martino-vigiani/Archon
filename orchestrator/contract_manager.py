"""
Contract Manager for living interface negotiations between terminals.

Transforms contracts from static JSON handoffs to living conversations.
Contracts are markdown files that track proposal/response/resolution cycles,
making the negotiation process visible and collaborative.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from .config import Config, TerminalID


class ContractStatus(Enum):
    """Status of a contract in its lifecycle."""

    NEGOTIATING = "negotiating"  # Proposal made, awaiting response
    AGREED = "agreed"  # Terms agreed, ready for implementation
    IMPLEMENTED = "implemented"  # Code written, awaiting verification
    VERIFIED = "verified"  # Verified working correctly
    DISPUTED = "disputed"  # Disagreement needs resolution
    DEPRECATED = "deprecated"  # No longer in use


@dataclass
class NegotiationEntry:
    """A single entry in a contract's negotiation history."""

    terminal: str  # Terminal ID or "orchestrator"
    timestamp: str
    action: Literal[
        "proposal", "response", "counter", "resolution", "implementation", "verification", "dispute"
    ]
    content: str
    code_block: str | None = None  # Optional code snippet
    quality: float | None = None  # Quality score for implementations (0.0-1.0)
    metadata: dict = field(default_factory=dict)

    def to_markdown(self) -> str:
        """Format entry as markdown section."""
        action_labels = {
            "proposal": "Proposal",
            "response": "Response",
            "counter": "Counter-Proposal",
            "resolution": "Resolution",
            "implementation": "Implementation",
            "verification": "Verification",
            "dispute": "Dispute",
        }

        time_str = self.timestamp.split("T")[1][:5] if "T" in self.timestamp else self.timestamp
        label = action_labels.get(self.action, self.action.capitalize())

        md = f"### {label} ({self.terminal.upper()} @ {time_str})\n\n"
        md += f"{self.content}\n"

        if self.code_block:
            # Detect language from content
            lang = "swift" if "struct" in self.code_block or "func" in self.code_block else ""
            lang = lang or (
                "typescript" if "interface" in self.code_block or ": {" in self.code_block else ""
            )
            lang = lang or "code"
            md += f"\n```{lang}\n{self.code_block}\n```\n"

        if self.quality is not None:
            md += f"\n**Quality:** {self.quality:.1%}\n"

        if self.metadata:
            if "file_path" in self.metadata:
                md += f"**File:** `{self.metadata['file_path']}`\n"
            if "agreed_by" in self.metadata:
                md += f"**Agreed by:** {', '.join(self.metadata['agreed_by'])}\n"

        return md + "\n"


@dataclass
class Contract:
    """
    A living contract between terminals.

    Contracts are conversations made visible - they track the full negotiation
    history from initial proposal through implementation and verification.
    """

    # Identity
    id: str
    name: str
    contract_type: str  # "interface", "api", "data_model", "protocol", "component"

    # Parties
    proposer: TerminalID
    implementer: TerminalID | None = None

    # Status
    status: ContractStatus = ContractStatus.NEGOTIATING

    # Negotiation history
    history: list[NegotiationEntry] = field(default_factory=list)

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    agreed_at: str | None = None
    implemented_at: str | None = None
    verified_at: str | None = None

    # Tags and metadata
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # Other contract IDs this depends on

    def to_markdown(self) -> str:
        """Render contract as a complete markdown document."""
        status_display = {
            ContractStatus.NEGOTIATING: "Negotiating",
            ContractStatus.AGREED: "Agreed",
            ContractStatus.IMPLEMENTED: "Implemented",
            ContractStatus.VERIFIED: "Verified",
            ContractStatus.DISPUTED: "Disputed",
            ContractStatus.DEPRECATED: "Deprecated",
        }

        md = f"# Contract: {self.name}\n\n"
        md += f"**ID:** `{self.id}`\n"
        md += f"**Type:** {self.contract_type}\n"
        md += f"**Status:** {status_display[self.status]}\n"
        md += f"**Proposer:** {self.proposer.upper()}\n"

        if self.implementer:
            md += f"**Implementer:** {self.implementer.upper()}\n"

        md += f"**Created:** {self.created_at}\n"
        md += f"**Updated:** {self.updated_at}\n"

        if self.agreed_at:
            md += f"**Agreed:** {self.agreed_at}\n"
        if self.implemented_at:
            md += f"**Implemented:** {self.implemented_at}\n"
        if self.verified_at:
            md += f"**Verified:** {self.verified_at}\n"

        if self.tags:
            md += f"**Tags:** {', '.join(self.tags)}\n"

        if self.dependencies:
            md += f"**Dependencies:** {', '.join(self.dependencies)}\n"

        md += "\n---\n\n"
        md += "## Negotiation History\n\n"

        for entry in self.history:
            md += entry.to_markdown()

        return md

    @classmethod
    def from_markdown(cls, content: str, file_path: Path) -> "Contract":
        """Parse a contract from markdown content."""
        # Extract header info
        id_match = re.search(r"\*\*ID:\*\*\s*`([^`]+)`", content)
        name_match = re.search(r"^#\s*Contract:\s*(.+)$", content, re.MULTILINE)
        type_match = re.search(r"\*\*Type:\*\*\s*(.+)$", content, re.MULTILINE)
        status_match = re.search(r"\*\*Status:\*\*\s*(.+)$", content, re.MULTILINE)
        proposer_match = re.search(r"\*\*Proposer:\*\*\s*(\w+)", content)
        implementer_match = re.search(r"\*\*Implementer:\*\*\s*(\w+)", content)
        created_match = re.search(r"\*\*Created:\*\*\s*(.+)$", content, re.MULTILINE)
        updated_match = re.search(r"\*\*Updated:\*\*\s*(.+)$", content, re.MULTILINE)
        agreed_match = re.search(r"\*\*Agreed:\*\*\s*(.+)$", content, re.MULTILINE)
        implemented_match = re.search(r"\*\*Implemented:\*\*\s*(.+)$", content, re.MULTILINE)
        verified_match = re.search(r"\*\*Verified:\*\*\s*(.+)$", content, re.MULTILINE)
        tags_match = re.search(r"\*\*Tags:\*\*\s*(.+)$", content, re.MULTILINE)
        deps_match = re.search(r"\*\*Dependencies:\*\*\s*(.+)$", content, re.MULTILINE)

        # Parse status
        status_str = status_match.group(1).strip().lower() if status_match else "negotiating"
        status_map = {
            "negotiating": ContractStatus.NEGOTIATING,
            "agreed": ContractStatus.AGREED,
            "implemented": ContractStatus.IMPLEMENTED,
            "verified": ContractStatus.VERIFIED,
            "disputed": ContractStatus.DISPUTED,
            "deprecated": ContractStatus.DEPRECATED,
        }
        status = status_map.get(status_str, ContractStatus.NEGOTIATING)

        # Parse history entries
        history = []
        history_section = re.search(r"## Negotiation History\s*\n(.+)", content, re.DOTALL)
        if history_section:
            entries = re.findall(
                r"###\s+(\w+(?:-\w+)?)\s+\((\w+)\s+@\s+(\d+:\d+)\)\s*\n\n(.*?)(?=\n###|\Z)",
                history_section.group(1),
                re.DOTALL,
            )
            for action_label, terminal, time, body in entries:
                action_map = {
                    "Proposal": "proposal",
                    "Response": "response",
                    "Counter-Proposal": "counter",
                    "Resolution": "resolution",
                    "Implementation": "implementation",
                    "Verification": "verification",
                    "Dispute": "dispute",
                }
                action = action_map.get(action_label, "response")

                # Extract code block if present
                code_match = re.search(r"```\w*\n(.*?)```", body, re.DOTALL)
                code_block = code_match.group(1).strip() if code_match else None

                # Extract quality if present
                quality_match = re.search(r"\*\*Quality:\*\*\s*([\d.]+)%", body)
                quality = float(quality_match.group(1)) / 100 if quality_match else None

                # Clean content (remove code block and metadata)
                content_text = body
                if code_match:
                    content_text = content_text.replace(code_match.group(0), "")
                content_text = re.sub(r"\*\*Quality:\*\*.*$", "", content_text, flags=re.MULTILINE)
                content_text = re.sub(r"\*\*File:\*\*.*$", "", content_text, flags=re.MULTILINE)
                content_text = content_text.strip()

                history.append(
                    NegotiationEntry(
                        terminal=terminal.lower(),
                        timestamp=f"2026-01-01T{time}:00",  # Placeholder date
                        action=action,
                        content=content_text,
                        code_block=code_block,
                        quality=quality,
                    )
                )

        # Build contract
        contract_id = id_match.group(1) if id_match else file_path.stem

        return cls(
            id=contract_id,
            name=name_match.group(1).strip() if name_match else file_path.stem,
            contract_type=type_match.group(1).strip() if type_match else "interface",
            proposer=proposer_match.group(1).lower() if proposer_match else "t1",  # type: ignore
            implementer=implementer_match.group(1).lower() if implementer_match else None,  # type: ignore
            status=status,
            history=history,
            created_at=(
                created_match.group(1).strip() if created_match else datetime.now().isoformat()
            ),
            updated_at=(
                updated_match.group(1).strip() if updated_match else datetime.now().isoformat()
            ),
            agreed_at=agreed_match.group(1).strip() if agreed_match else None,
            implemented_at=implemented_match.group(1).strip() if implemented_match else None,
            verified_at=verified_match.group(1).strip() if verified_match else None,
            tags=[t.strip() for t in tags_match.group(1).split(",")] if tags_match else [],
            dependencies=[d.strip() for d in deps_match.group(1).split(",")] if deps_match else [],
        )


class ContractManager:
    """
    Manages living contract negotiations between terminals.

    Contracts are conversations made visible, not bureaucratic handoffs.
    Each contract is a markdown file that tracks the full negotiation history,
    enabling transparent collaboration and conflict resolution.

    Typical flow:
    1. T1 proposes a contract: "I need a UserProfile with these fields..."
    2. T2 responds: "I can do that, but suggest adding createdAt"
    3. T4 mediates if needed: "Let's ship with createdAt, revisit later"
    4. Agreement reached, status moves to AGREED
    5. T2 implements and marks IMPLEMENTED with quality score
    6. T5 verifies and marks VERIFIED
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

    @property
    def templates_dir(self) -> Path:
        """Get the contract templates directory."""
        return self.config.base_dir / "templates" / "contracts"

    def _ensure_dirs(self) -> None:
        """Create contracts directory if it doesn't exist."""
        self.contracts_dir.mkdir(parents=True, exist_ok=True)

    def _generate_contract_id(self, name: str) -> str:
        """Generate a unique contract ID."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_name = re.sub(r"[^a-zA-Z0-9]", "", name)[:20].lower()
        return f"contract_{safe_name}_{timestamp}"

    def _get_contract_path(self, contract_id: str) -> Path:
        """Get the path to a contract file."""
        return self.contracts_dir / f"{contract_id}.md"

    # -------------------------------------------------------------------------
    # Core Negotiation Methods
    # -------------------------------------------------------------------------

    def propose_contract(
        self,
        from_terminal: TerminalID,
        name: str,
        contract_type: str,
        content: str,
        code_block: str | None = None,
        tags: list[str] | None = None,
        dependencies: list[str] | None = None,
    ) -> Contract:
        """
        Propose a new contract.

        This is the start of a negotiation. The proposing terminal defines
        what they need, and other terminals can respond with modifications
        or agreements.

        Args:
            from_terminal: Terminal making the proposal (e.g., "t1")
            name: Human-readable contract name (e.g., "UserProfile")
            contract_type: Type of contract ("interface", "api", "data_model", "protocol", "component")
            content: Description of what's being proposed
            code_block: Optional code snippet defining the interface
            tags: Optional tags for categorization
            dependencies: Optional list of other contract IDs this depends on

        Returns:
            The created Contract object

        Raises:
            ValueError: If a contract with this name already exists
        """
        # Check for existing contract with same name
        existing = self.get_contract_by_name(name)
        if existing and existing.status not in [ContractStatus.DEPRECATED]:
            raise ValueError(
                f"Contract '{name}' already exists with status {existing.status.value}. "
                "Use respond_to_contract to engage with existing contracts."
            )

        contract_id = self._generate_contract_id(name)
        now = datetime.now().isoformat()

        # Create initial proposal entry
        proposal = NegotiationEntry(
            terminal=from_terminal,
            timestamp=now,
            action="proposal",
            content=content,
            code_block=code_block,
        )

        contract = Contract(
            id=contract_id,
            name=name,
            contract_type=contract_type,
            proposer=from_terminal,
            status=ContractStatus.NEGOTIATING,
            history=[proposal],
            created_at=now,
            updated_at=now,
            tags=tags or [],
            dependencies=dependencies or [],
        )

        # Save contract
        self._save_contract(contract)

        return contract

    def respond_to_contract(
        self,
        terminal: TerminalID,
        contract_id: str,
        response: str,
        code_block: str | None = None,
        action: Literal["response", "counter", "agree", "dispute"] = "response",
    ) -> Contract:
        """
        Respond to an existing contract proposal.

        Terminals can respond in different ways:
        - "response": General feedback or questions
        - "counter": Counter-proposal with modifications
        - "agree": Accept the current proposal (moves to AGREED if all parties agree)
        - "dispute": Flag an issue that needs resolution

        Args:
            terminal: Terminal making the response
            contract_id: ID of the contract to respond to
            response: Response content
            code_block: Optional modified code snippet
            action: Type of response

        Returns:
            The updated Contract object

        Raises:
            ValueError: If contract doesn't exist or is in wrong state
        """
        contract = self.get_contract(contract_id)
        if not contract:
            raise ValueError(f"Contract '{contract_id}' not found")

        if contract.status in [ContractStatus.VERIFIED, ContractStatus.DEPRECATED]:
            raise ValueError(
                f"Contract '{contract_id}' is {contract.status.value} and cannot be modified"
            )

        now = datetime.now().isoformat()

        # Map action to entry type
        action_map = {
            "response": "response",
            "counter": "counter",
            "agree": "response",
            "dispute": "dispute",
        }

        entry = NegotiationEntry(
            terminal=terminal,
            timestamp=now,
            action=action_map[action],
            content=response,
            code_block=code_block,
        )

        contract.history.append(entry)
        contract.updated_at = now

        # Handle state transitions
        if action == "agree":
            # Check if enough parties have agreed
            agreeing_parties = set()
            for e in contract.history:
                if "agree" in e.content.lower() or e.action == "resolution":
                    agreeing_parties.add(e.terminal)

            # Need at least proposer and one implementer to agree
            if len(agreeing_parties) >= 2 or terminal != contract.proposer:
                contract.status = ContractStatus.AGREED
                contract.agreed_at = now
                contract.implementer = terminal if terminal != contract.proposer else None

        elif action == "dispute":
            contract.status = ContractStatus.DISPUTED

        self._save_contract(contract)
        return contract

    def resolve_contract(
        self,
        terminal: TerminalID,
        contract_id: str,
        resolution: str,
        code_block: str | None = None,
    ) -> Contract:
        """
        Mediate and resolve a contract negotiation.

        Typically used by T4 (strategy) to break deadlocks or finalize agreements.
        This moves the contract to AGREED status.

        Args:
            terminal: Terminal providing resolution (typically "t4")
            contract_id: ID of the contract to resolve
            resolution: Resolution description
            code_block: Final agreed-upon interface

        Returns:
            The updated Contract object
        """
        contract = self.get_contract(contract_id)
        if not contract:
            raise ValueError(f"Contract '{contract_id}' not found")

        now = datetime.now().isoformat()

        entry = NegotiationEntry(
            terminal=terminal,
            timestamp=now,
            action="resolution",
            content=resolution,
            code_block=code_block,
            metadata={"mediated": True},
        )

        contract.history.append(entry)
        contract.status = ContractStatus.AGREED
        contract.agreed_at = now
        contract.updated_at = now

        self._save_contract(contract)
        return contract

    def implement_contract(
        self,
        terminal: TerminalID,
        contract_id: str,
        details: str,
        file_path: str | None = None,
        code_block: str | None = None,
        quality: float = 0.8,
    ) -> Contract:
        """
        Mark a contract as implemented.

        The implementing terminal provides details about where and how
        the contract was implemented, along with a self-assessed quality score.

        Args:
            terminal: Terminal that implemented the contract
            contract_id: ID of the contract
            details: Description of the implementation
            file_path: Path to the implementation file
            code_block: Implementation code snippet
            quality: Self-assessed quality score (0.0-1.0)

        Returns:
            The updated Contract object

        Raises:
            ValueError: If contract is not in AGREED status
        """
        contract = self.get_contract(contract_id)
        if not contract:
            raise ValueError(f"Contract '{contract_id}' not found")

        if contract.status not in [ContractStatus.AGREED, ContractStatus.NEGOTIATING]:
            # Allow implementation even from NEGOTIATING for rapid iteration
            pass

        now = datetime.now().isoformat()

        metadata = {}
        if file_path:
            metadata["file_path"] = file_path

        entry = NegotiationEntry(
            terminal=terminal,
            timestamp=now,
            action="implementation",
            content=details,
            code_block=code_block,
            quality=quality,
            metadata=metadata,
        )

        contract.history.append(entry)
        contract.status = ContractStatus.IMPLEMENTED
        contract.implemented_at = now
        contract.updated_at = now
        contract.implementer = terminal

        self._save_contract(contract)
        return contract

    def verify_contract(
        self,
        terminal: TerminalID,
        contract_id: str,
        verified: bool,
        notes: str,
        quality: float | None = None,
    ) -> Contract:
        """
        Verify a contract implementation.

        Typically done by T5 (QA) to confirm that the implementation
        matches the agreed contract.

        Args:
            terminal: Terminal doing verification (typically "t5")
            contract_id: ID of the contract
            verified: Whether the implementation matches the contract
            notes: Verification notes
            quality: Optional quality assessment override

        Returns:
            The updated Contract object
        """
        contract = self.get_contract(contract_id)
        if not contract:
            raise ValueError(f"Contract '{contract_id}' not found")

        now = datetime.now().isoformat()

        entry = NegotiationEntry(
            terminal=terminal,
            timestamp=now,
            action="verification",
            content=notes,
            quality=quality,
            metadata={"verified": verified},
        )

        contract.history.append(entry)
        contract.updated_at = now

        if verified:
            contract.status = ContractStatus.VERIFIED
            contract.verified_at = now
        else:
            # Failed verification - needs rework
            contract.status = ContractStatus.DISPUTED

        self._save_contract(contract)
        return contract

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    def get_contract(self, contract_id: str) -> Contract | None:
        """
        Get a contract by ID.

        Args:
            contract_id: Contract ID

        Returns:
            Contract object if exists, None otherwise
        """
        # Try exact path first
        contract_path = self._get_contract_path(contract_id)
        if contract_path.exists():
            return self._load_contract(contract_path)

        # Search by partial ID
        for path in self.contracts_dir.glob("*.md"):
            if contract_id in path.stem:
                return self._load_contract(path)

        return None

    def get_contract_by_name(self, name: str) -> Contract | None:
        """
        Get a contract by its human-readable name.

        Args:
            name: Contract name

        Returns:
            Contract object if exists, None otherwise
        """
        name_lower = name.lower()
        for path in self.contracts_dir.glob("*.md"):
            contract = self._load_contract(path)
            if contract and contract.name.lower() == name_lower:
                return contract
        return None

    def list_contracts(
        self,
        status: ContractStatus | None = None,
        terminal: TerminalID | None = None,
        contract_type: str | None = None,
    ) -> list[Contract]:
        """
        List contracts with optional filtering.

        Args:
            status: Filter by status
            terminal: Filter by involved terminal (proposer or implementer)
            contract_type: Filter by contract type

        Returns:
            List of matching contracts
        """
        contracts = []

        for path in self.contracts_dir.glob("*.md"):
            contract = self._load_contract(path)
            if not contract:
                continue

            # Apply filters
            if status and contract.status != status:
                continue
            if terminal and terminal not in [contract.proposer, contract.implementer]:
                continue
            if contract_type and contract.contract_type != contract_type:
                continue

            contracts.append(contract)

        # Sort by updated_at descending
        contracts.sort(key=lambda c: c.updated_at, reverse=True)
        return contracts

    def list_pending_contracts(self, for_terminal: TerminalID | None = None) -> list[Contract]:
        """
        List contracts awaiting action.

        Args:
            for_terminal: Optional filter for contracts relevant to this terminal

        Returns:
            List of contracts in NEGOTIATING or AGREED status
        """
        pending = []

        for contract in self.list_contracts():
            if contract.status in [ContractStatus.NEGOTIATING, ContractStatus.AGREED]:
                if for_terminal:
                    # Check if this terminal should act on this contract
                    if contract.proposer == for_terminal:
                        continue  # Proposer is waiting for response
                    if (
                        contract.status == ContractStatus.AGREED
                        and contract.implementer == for_terminal
                    ):
                        pending.append(contract)  # Should implement
                    elif contract.status == ContractStatus.NEGOTIATING:
                        pending.append(contract)  # Can respond
                else:
                    pending.append(contract)

        return pending

    def get_contracts_for_terminal(
        self,
        terminal_id: TerminalID,
        role: Literal["proposer", "implementer", "all"] = "all",
    ) -> list[Contract]:
        """
        Get contracts relevant to a specific terminal.

        Args:
            terminal_id: Terminal identifier
            role: Filter by role in contract

        Returns:
            List of relevant contracts
        """
        contracts = []

        for contract in self.list_contracts():
            if (
                role == "proposer"
                and contract.proposer == terminal_id
                or role == "implementer"
                and contract.implementer == terminal_id
                or role == "all"
                and terminal_id in [contract.proposer, contract.implementer]
            ):
                contracts.append(contract)

        return contracts

    # -------------------------------------------------------------------------
    # Summary and Context Methods
    # -------------------------------------------------------------------------

    def get_contract_summary(self) -> str:
        """
        Get a human-readable summary of all contracts.

        Returns:
            Formatted markdown string with contract overview
        """
        contracts = self.list_contracts()

        if not contracts:
            return "# Contract Summary\n\nNo contracts defined yet."

        # Group by status
        by_status: dict[ContractStatus, list[Contract]] = {status: [] for status in ContractStatus}
        for contract in contracts:
            by_status[contract.status].append(contract)

        lines = ["# Contract Summary\n"]
        lines.append(f"**Total:** {len(contracts)} contracts\n")

        for status in [
            ContractStatus.NEGOTIATING,
            ContractStatus.DISPUTED,
            ContractStatus.AGREED,
            ContractStatus.IMPLEMENTED,
            ContractStatus.VERIFIED,
        ]:
            status_contracts = by_status[status]
            if status_contracts:
                emoji_map = {
                    ContractStatus.NEGOTIATING: "Negotiating",
                    ContractStatus.DISPUTED: "Disputed",
                    ContractStatus.AGREED: "Agreed",
                    ContractStatus.IMPLEMENTED: "Implemented",
                    ContractStatus.VERIFIED: "Verified",
                }

                lines.append(f"\n## {emoji_map[status]} ({len(status_contracts)})\n")

                for contract in status_contracts:
                    lines.append(
                        f"- **{contract.name}** ({contract.contract_type}) - "
                        f"{contract.proposer.upper()} -> {contract.implementer.upper() if contract.implementer else '?'}"
                    )

        return "\n".join(lines)

    def get_negotiation_context(self, contract_id: str) -> str:
        """
        Get the full negotiation context for a contract.

        Useful for providing context to terminals about ongoing negotiations.

        Args:
            contract_id: Contract ID

        Returns:
            Formatted markdown with negotiation history
        """
        contract = self.get_contract(contract_id)
        if not contract:
            return f"Contract '{contract_id}' not found."

        return contract.to_markdown()

    # -------------------------------------------------------------------------
    # Persistence Methods
    # -------------------------------------------------------------------------

    def _save_contract(self, contract: Contract) -> Path:
        """Save a contract to disk."""
        path = self._get_contract_path(contract.id)
        path.write_text(contract.to_markdown())
        return path

    def _load_contract(self, path: Path) -> Contract | None:
        """Load a contract from disk."""
        try:
            content = path.read_text()
            return Contract.from_markdown(content, path)
        except Exception as e:
            print(f"[ContractManager] Error loading {path}: {e}")
            return None

    def delete_contract(self, contract_id: str) -> bool:
        """
        Delete a contract.

        Args:
            contract_id: Contract ID

        Returns:
            True if deleted, False if not found
        """
        path = self._get_contract_path(contract_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def clear_contracts(self) -> None:
        """Clear all contracts."""
        for path in self.contracts_dir.glob("*.md"):
            path.unlink()

    def deprecate_contract(self, contract_id: str, reason: str) -> Contract | None:
        """
        Mark a contract as deprecated.

        Args:
            contract_id: Contract ID
            reason: Reason for deprecation

        Returns:
            Updated contract or None if not found
        """
        contract = self.get_contract(contract_id)
        if not contract:
            return None

        now = datetime.now().isoformat()

        entry = NegotiationEntry(
            terminal="orchestrator",
            timestamp=now,
            action="response",
            content=f"**DEPRECATED:** {reason}",
        )

        contract.history.append(entry)
        contract.status = ContractStatus.DEPRECATED
        contract.updated_at = now

        self._save_contract(contract)
        return contract


# Legacy compatibility - map old status strings to new enum
def _legacy_status_to_enum(status: str) -> ContractStatus:
    """Convert legacy status string to ContractStatus enum."""
    mapping = {
        "proposed": ContractStatus.NEGOTIATING,
        "implemented": ContractStatus.IMPLEMENTED,
        "verified": ContractStatus.VERIFIED,
    }
    return mapping.get(status, ContractStatus.NEGOTIATING)
