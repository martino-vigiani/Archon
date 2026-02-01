"""
Message Bus for inter-terminal communication.

Uses file-based messaging in .orchestra/messages/ for coordination.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from .config import Config, TerminalID


MessageType = Literal["request", "response", "broadcast", "status", "artifact"]


@dataclass
class Message:
    """A message between terminals or from orchestrator."""

    id: str
    sender: str  # Terminal ID or "orchestrator"
    recipient: str  # Terminal ID, "all", or "orchestrator"
    type: MessageType
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)
    read: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "type": self.type,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "read": self.read,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(**data)

    def to_markdown(self) -> str:
        """Format message as markdown for terminal consumption."""
        return f"""---
## Message: {self.id}
**From:** {self.sender}
**To:** {self.recipient}
**Type:** {self.type}
**Time:** {self.timestamp}

{self.content}

---
"""


class MessageBus:
    """
    File-based message bus for terminal communication.

    Each terminal has an inbox file that it monitors.
    Broadcast messages go to all terminals.
    """

    def __init__(self, config: Config):
        self.config = config
        self._message_counter = 0
        self._ensure_files()

    def _ensure_files(self) -> None:
        """Create message files if they don't exist."""
        self.config.ensure_dirs()

        # Create inbox files for each terminal
        for tid in ["t1", "t2", "t3", "t4"]:
            inbox = self.config.get_terminal_inbox(tid)  # type: ignore
            if not inbox.exists():
                inbox.write_text("# Inbox\n\nNo messages yet.\n")

        # Create broadcast file
        broadcast = self.config.get_broadcast_file()
        if not broadcast.exists():
            broadcast.write_text("# Broadcast Channel\n\nNo broadcasts yet.\n")

    def _generate_message_id(self) -> str:
        """Generate a unique message ID."""
        self._message_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"msg_{timestamp}_{self._message_counter:04d}"

    def send(
        self,
        sender: str,
        recipient: str,
        content: str,
        msg_type: MessageType = "request",
        metadata: dict | None = None,
    ) -> Message:
        """Send a message to a terminal or broadcast to all."""
        msg = Message(
            id=self._generate_message_id(),
            sender=sender,
            recipient=recipient,
            type=msg_type,
            content=content,
            metadata=metadata or {},
        )

        if recipient == "all":
            self._append_to_broadcast(msg)
            # Also append to each terminal's inbox
            for tid in ["t1", "t2", "t3", "t4"]:
                self._append_to_inbox(tid, msg)  # type: ignore
        else:
            self._append_to_inbox(recipient, msg)  # type: ignore

        return msg

    def _append_to_inbox(self, terminal_id: TerminalID, msg: Message) -> None:
        """Append a message to a terminal's inbox."""
        inbox = self.config.get_terminal_inbox(terminal_id)
        current = inbox.read_text() if inbox.exists() else ""

        # Remove "No messages yet." if present
        if "No messages yet." in current:
            current = "# Inbox\n\n"

        inbox.write_text(current + msg.to_markdown())

    def _append_to_broadcast(self, msg: Message) -> None:
        """Append a message to the broadcast channel."""
        broadcast = self.config.get_broadcast_file()
        current = broadcast.read_text() if broadcast.exists() else ""

        if "No broadcasts yet." in current:
            current = "# Broadcast Channel\n\n"

        broadcast.write_text(current + msg.to_markdown())

    def read_inbox(self, terminal_id: TerminalID) -> str:
        """Read a terminal's inbox content."""
        inbox = self.config.get_terminal_inbox(terminal_id)
        return inbox.read_text() if inbox.exists() else ""

    def read_broadcast(self) -> str:
        """Read the broadcast channel content."""
        broadcast = self.config.get_broadcast_file()
        return broadcast.read_text() if broadcast.exists() else ""

    def clear_inbox(self, terminal_id: TerminalID) -> None:
        """Clear a terminal's inbox after processing."""
        inbox = self.config.get_terminal_inbox(terminal_id)
        inbox.write_text("# Inbox\n\nNo messages yet.\n")

    def clear_all(self) -> None:
        """Clear all message files."""
        for tid in ["t1", "t2", "t3", "t4"]:
            self.clear_inbox(tid)  # type: ignore

        broadcast = self.config.get_broadcast_file()
        broadcast.write_text("# Broadcast Channel\n\nNo broadcasts yet.\n")

    def broadcast_status(self, status: str, metadata: dict | None = None) -> Message:
        """Broadcast a status update to all terminals."""
        return self.send(
            sender="orchestrator",
            recipient="all",
            content=status,
            msg_type="status",
            metadata=metadata or {},
        )

    def request_from_terminal(
        self,
        from_terminal: TerminalID,
        to_terminal: TerminalID,
        request: str,
    ) -> Message:
        """Send a request from one terminal to another."""
        return self.send(
            sender=from_terminal,
            recipient=to_terminal,
            content=request,
            msg_type="request",
        )

    def share_artifact(
        self,
        sender: str,
        artifact_name: str,
        artifact_path: str,
        description: str,
    ) -> Message:
        """Share an artifact with all terminals."""
        content = f"""## Artifact: {artifact_name}

**Path:** `{artifact_path}`

{description}
"""
        return self.send(
            sender=sender,
            recipient="all",
            content=content,
            msg_type="artifact",
            metadata={"artifact_name": artifact_name, "artifact_path": artifact_path},
        )
