"""
Tests for the Message Bus inter-terminal communication system.

The MessageBus provides file-based messaging between terminals:
- Direct messages: Terminal-to-terminal communication
- Broadcasts: Messages to all terminals
- Artifact sharing: File/component announcements
- Status updates: Orchestrator coordination messages

Critical edge cases:
- Broadcast reaches all 5 inboxes
- "No messages yet" placeholder is cleaned on first real message
- Message IDs are unique across rapid successive calls
"""

from orchestrator.config import Config
from orchestrator.message_bus import Message, MessageBus


class TestMessageDataclass:
    """Test Message creation and serialization."""

    def test_message_to_dict(self) -> None:
        """Message to_dict should contain all fields."""
        msg = Message(
            id="msg_001",
            sender="t1",
            recipient="t2",
            type="request",
            content="Need UserService API",
            metadata={"priority": "high"},
        )

        d = msg.to_dict()

        assert d["id"] == "msg_001"
        assert d["sender"] == "t1"
        assert d["recipient"] == "t2"
        assert d["type"] == "request"
        assert d["content"] == "Need UserService API"
        assert d["metadata"] == {"priority": "high"}
        assert d["read"] is False

    def test_message_to_markdown_format(self) -> None:
        """Markdown output should contain all fields."""
        msg = Message(
            id="msg_test",
            sender="t1",
            recipient="t2",
            type="request",
            content="Build the model",
        )

        md = msg.to_markdown()

        assert "msg_test" in md
        assert "t1" in md
        assert "t2" in md
        assert "request" in md
        assert "Build the model" in md

    def test_message_default_read_is_false(self) -> None:
        """New messages should default to unread."""
        msg = Message(
            id="msg_002",
            sender="t1",
            recipient="t2",
            type="request",
            content="test",
        )
        assert msg.read is False

    def test_message_timestamp_auto_generated(self) -> None:
        """Messages should auto-generate a timestamp."""
        msg = Message(
            id="msg_003",
            sender="t1",
            recipient="t2",
            type="request",
            content="test",
        )
        assert msg.timestamp is not None
        assert "T" in msg.timestamp  # ISO format


class TestMessageBusInit:
    """Test MessageBus initialization."""

    def test_creates_inbox_files_for_all_terminals(self, config: Config) -> None:
        """Should create inbox files for t1-t5."""
        MessageBus(config)

        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            inbox = config.get_terminal_inbox(tid)  # type: ignore
            assert inbox.exists(), f"Inbox for {tid} should exist"

    def test_creates_broadcast_file(self, config: Config) -> None:
        """Should create the broadcast channel file."""
        MessageBus(config)

        broadcast = config.get_broadcast_file()
        assert broadcast.exists()

    def test_inbox_starts_with_placeholder(self, config: Config) -> None:
        """New inbox should contain 'No messages yet' placeholder."""
        bus = MessageBus(config)

        content = bus.read_inbox("t1")
        assert "No messages yet" in content


class TestDirectMessages:
    """Test terminal-to-terminal messaging."""

    def test_send_direct_message(self, config: Config) -> None:
        """Can send a direct message to a specific terminal."""
        bus = MessageBus(config)

        msg = bus.send(
            sender="t1",
            recipient="t2",
            content="Need your UserService API",
            msg_type="request",
        )

        assert msg.id.startswith("msg_")
        assert msg.sender == "t1"
        assert msg.recipient == "t2"

    def test_direct_message_appears_in_recipient_inbox(self, config: Config) -> None:
        """Direct messages should appear in the recipient's inbox."""
        bus = MessageBus(config)

        bus.send(sender="t1", recipient="t2", content="Hello T2")

        inbox = bus.read_inbox("t2")
        assert "Hello T2" in inbox
        assert "No messages yet" not in inbox

    def test_direct_message_not_in_other_inboxes(self, config: Config) -> None:
        """Direct messages should NOT appear in other terminals' inboxes."""
        bus = MessageBus(config)

        bus.send(sender="t1", recipient="t2", content="Private to T2")

        # T3 should not see T2's message
        t3_inbox = bus.read_inbox("t3")
        assert "Private to T2" not in t3_inbox



class TestBroadcastMessages:
    """Test broadcast messaging to all terminals."""

    def test_broadcast_reaches_all_inboxes(self, config: Config) -> None:
        """Broadcast should appear in every terminal's inbox."""
        bus = MessageBus(config)

        bus.send(sender="orchestrator", recipient="all", content="Phase 1 starting")

        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            inbox = bus.read_inbox(tid)  # type: ignore
            assert "Phase 1 starting" in inbox, f"{tid} inbox should contain broadcast"

    def test_broadcast_appears_in_broadcast_file(self, config: Config) -> None:
        """Broadcast messages should also go to the broadcast file."""
        bus = MessageBus(config)

        bus.send(sender="orchestrator", recipient="all", content="Global update")

        broadcast = bus.read_broadcast()
        assert "Global update" in broadcast

    def test_broadcast_status_convenience(self, config: Config) -> None:
        """broadcast_status should send a status-type broadcast."""
        bus = MessageBus(config)

        msg = bus.broadcast_status("All terminals ready")

        assert msg.type == "status"
        assert msg.sender == "orchestrator"
        assert msg.recipient == "all"

    def test_broadcast_clears_placeholder(self, config: Config) -> None:
        """First broadcast should clear 'No messages yet' from all inboxes."""
        bus = MessageBus(config)

        bus.send(sender="orchestrator", recipient="all", content="First message")

        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            inbox = bus.read_inbox(tid)  # type: ignore
            assert "No messages yet" not in inbox


class TestMessageIDUniqueness:
    """Test that message IDs are unique."""

    def test_sequential_ids_are_unique(self, config: Config) -> None:
        """Rapid successive messages should have unique IDs."""
        bus = MessageBus(config)

        ids = set()
        for _ in range(10):
            msg = bus.send(sender="t1", recipient="t2", content="test")
            ids.add(msg.id)

        assert len(ids) == 10, "All 10 message IDs should be unique"


class TestInboxManagement:
    """Test inbox clearing and management."""

    def test_clear_inbox(self, config: Config) -> None:
        """Clearing inbox should remove all messages."""
        bus = MessageBus(config)

        bus.send(sender="t1", recipient="t2", content="Message 1")
        bus.send(sender="t3", recipient="t2", content="Message 2")

        bus.clear_inbox("t2")

        inbox = bus.read_inbox("t2")
        assert "No messages yet" in inbox
        assert "Message 1" not in inbox
        assert "Message 2" not in inbox

    def test_clear_all(self, config: Config) -> None:
        """clear_all should reset all inboxes and broadcast."""
        bus = MessageBus(config)

        bus.send(sender="orchestrator", recipient="all", content="Broadcast")
        bus.send(sender="t1", recipient="t2", content="Direct")

        bus.clear_all()

        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            inbox = bus.read_inbox(tid)  # type: ignore
            assert "No messages yet" in inbox

        broadcast = bus.read_broadcast()
        assert "No broadcasts yet" in broadcast

    def test_multiple_messages_accumulate(self, config: Config) -> None:
        """Multiple messages to same inbox should accumulate."""
        bus = MessageBus(config)

        bus.send(sender="t1", recipient="t2", content="First message")
        bus.send(sender="t3", recipient="t2", content="Second message")

        inbox = bus.read_inbox("t2")
        assert "First message" in inbox
        assert "Second message" in inbox


class TestMessageMetadata:
    """Test message metadata handling."""

    def test_metadata_preserved(self, config: Config) -> None:
        """Message metadata should be preserved."""
        bus = MessageBus(config)

        msg = bus.send(
            sender="t1",
            recipient="t2",
            content="Priority task",
            metadata={"urgency": "critical", "retry_count": 0},
        )

        assert msg.metadata["urgency"] == "critical"
        assert msg.metadata["retry_count"] == 0

    def test_none_metadata_becomes_empty_dict(self, config: Config) -> None:
        """None metadata should be converted to empty dict."""
        bus = MessageBus(config)

        msg = bus.send(sender="t1", recipient="t2", content="test", metadata=None)

        assert msg.metadata == {}
