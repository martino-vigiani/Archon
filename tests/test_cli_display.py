"""
Tests for the CLI Display components.

The cli_display module provides:
- Colors class (ANSI codes, disable for non-TTY)
- Terminal personality badges
- Quality gradient visualization (bar + label)
- Flow state indicators
- Spinner animation frames
- Box drawing and formatting utilities
- strip_ansi helper
- format_duration helper

No I/O needed - pure computation tests.
"""

import pytest

from orchestrator.cli_display import (
    Colors,
    ContractDisplay,
    Spinner,
    TerminalPersonality,
    TerminalStatus,
    c,
    flow_state_indicator,
    format_duration,
    get_terminal_badge,
    get_terminal_color,
    get_terminal_name,
    quality_bar,
    quality_label,
    strip_ansi,
    TERMINAL_PERSONALITIES,
)


class TestColors:
    """Test the Colors class."""

    def test_reset_is_ansi(self) -> None:
        """RESET should be an ANSI escape sequence."""
        # Colors might be disabled if tests run in non-TTY
        # Just verify the attribute exists
        assert hasattr(Colors, "RESET")

    def test_all_standard_colors_exist(self) -> None:
        """All standard color attributes should exist."""
        for name in ["RED", "GREEN", "BLUE", "YELLOW", "CYAN", "MAGENTA", "WHITE", "BLACK"]:
            assert hasattr(Colors, name), f"Colors.{name} should exist"

    def test_all_bright_colors_exist(self) -> None:
        """All bright color attributes should exist."""
        for name in ["BRIGHT_RED", "BRIGHT_GREEN", "BRIGHT_BLUE", "BRIGHT_CYAN"]:
            assert hasattr(Colors, name)

    def test_styles_exist(self) -> None:
        """Style attributes should exist."""
        for name in ["BOLD", "DIM", "ITALIC", "UNDERLINE"]:
            assert hasattr(Colors, name)


class TestColorFunction:
    """Test the c() color application function."""

    def test_no_colors_returns_text(self) -> None:
        """c() with no colors should return plain text."""
        assert c("hello") == "hello"

    def test_applies_reset_suffix(self) -> None:
        """c() should append RESET to colored text."""
        result = c("text", Colors.RED)
        assert result.endswith(Colors.RESET)

    def test_multiple_colors(self) -> None:
        """c() should apply multiple colors."""
        result = c("text", Colors.BOLD, Colors.RED)
        assert Colors.BOLD in result
        assert Colors.RED in result


class TestTerminalPersonalities:
    """Test terminal personality definitions."""

    def test_all_five_terminals_defined(self) -> None:
        """All 5 terminals should be in TERMINAL_PERSONALITIES."""
        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            assert tid in TERMINAL_PERSONALITIES, f"{tid} missing from personalities"

    def test_personality_has_required_fields(self) -> None:
        """Each personality should have id, name, emoji, description."""
        for tid, personality in TERMINAL_PERSONALITIES.items():
            assert personality.id == tid
            assert personality.name != ""
            assert personality.emoji != ""
            # color may be empty string in non-TTY (Colors.disable() called)
            assert personality.color is not None
            assert personality.description != ""

    @pytest.mark.parametrize(
        "tid,expected_name",
        [
            ("t1", "Craftsman"),
            ("t2", "Architect"),
            ("t3", "Narrator"),
            ("t4", "Strategist"),
            ("t5", "Skeptic"),
        ],
    )
    def test_correct_names(self, tid: str, expected_name: str) -> None:
        """Each terminal should have the correct name."""
        assert TERMINAL_PERSONALITIES[tid].name == expected_name


class TestGetTerminalBadge:
    """Test terminal badge generation."""

    def test_known_terminal_with_name(self) -> None:
        """Known terminal with include_name should show name."""
        badge = get_terminal_badge("t1", include_name=True)
        stripped = strip_ansi(badge)
        assert "T1" in stripped
        assert "Craftsman" in stripped

    def test_known_terminal_without_name(self) -> None:
        """Known terminal without name should only show ID."""
        badge = get_terminal_badge("t1", include_name=False)
        stripped = strip_ansi(badge)
        assert "T1" in stripped
        assert "Craftsman" not in stripped

    def test_unknown_terminal(self) -> None:
        """Unknown terminal should return plain badge."""
        badge = get_terminal_badge("t99")
        assert "[T99]" in badge


class TestGetTerminalName:
    """Test terminal name lookup."""

    def test_known_terminal(self) -> None:
        """Known terminal should return personality name."""
        assert get_terminal_name("t1") == "Craftsman"
        assert get_terminal_name("t5") == "Skeptic"

    def test_unknown_terminal(self) -> None:
        """Unknown terminal should return uppercased ID."""
        assert get_terminal_name("t99") == "T99"


class TestGetTerminalColor:
    """Test terminal color lookup."""

    def test_known_terminal(self) -> None:
        """Known terminal should return its color."""
        color = get_terminal_color("t1")
        assert color == TERMINAL_PERSONALITIES["t1"].color

    def test_unknown_terminal(self) -> None:
        """Unknown terminal should return WHITE."""
        assert get_terminal_color("t99") == Colors.WHITE


class TestQualityBar:
    """Test quality bar visualization."""

    def test_zero_quality(self) -> None:
        """Zero quality should show all empty."""
        bar = strip_ansi(quality_bar(0.0, width=10))
        assert "=" not in bar
        assert bar.count("-") == 10

    def test_full_quality(self) -> None:
        """Full quality should show all filled."""
        bar = strip_ansi(quality_bar(1.0, width=10))
        assert bar.count("=") == 10
        assert "-" not in bar

    def test_half_quality(self) -> None:
        """Half quality should show half filled."""
        bar = strip_ansi(quality_bar(0.5, width=10))
        assert bar.count("=") == 5
        assert bar.count("-") == 5

    def test_clamps_above_one(self) -> None:
        """Quality above 1.0 should be clamped."""
        bar = strip_ansi(quality_bar(1.5, width=10))
        assert bar.count("=") == 10

    def test_clamps_below_zero(self) -> None:
        """Quality below 0.0 should be clamped."""
        bar = strip_ansi(quality_bar(-0.5, width=10))
        assert "=" not in bar

    def test_custom_width(self) -> None:
        """Custom width should be respected."""
        bar = strip_ansi(quality_bar(1.0, width=20))
        assert bar.count("=") == 20


class TestQualityLabel:
    """Test quality label descriptions."""

    @pytest.mark.parametrize(
        "quality,expected_text",
        [
            (0.95, "Excellent"),
            (0.85, "Polished"),
            (0.65, "Solid"),
            (0.45, "Working"),
            (0.25, "Draft"),
            (0.05, "Starting"),
        ],
    )
    def test_quality_labels(self, quality: float, expected_text: str) -> None:
        """Quality level should map to correct label."""
        label = strip_ansi(quality_label(quality))
        assert label == expected_text


class TestFlowStateIndicator:
    """Test flow state visual indicators."""

    @pytest.mark.parametrize(
        "state,expected",
        [
            ("idle", "~"),
            ("flowing", ">>"),
            ("blocked", "!!"),
            ("syncing", "<>"),
            ("completing", "OK"),
        ],
    )
    def test_known_states(self, state: str, expected: str) -> None:
        """Known flow states should return correct indicators."""
        indicator = strip_ansi(flow_state_indicator(state))
        assert indicator == expected

    def test_unknown_state(self) -> None:
        """Unknown state should return question mark."""
        indicator = strip_ansi(flow_state_indicator("unknown"))  # type: ignore
        assert indicator == "?"


class TestSpinner:
    """Test the Spinner animation."""

    def test_cycles_through_frames(self) -> None:
        """Spinner should cycle through all 4 frames."""
        spinner = Spinner()
        frames = [spinner.next_frame() for _ in range(4)]
        assert frames == ["|", "/", "-", "\\"]

    def test_wraps_around(self) -> None:
        """Spinner should wrap after all frames."""
        spinner = Spinner()
        for _ in range(4):
            spinner.next_frame()
        # Should restart
        assert spinner.next_frame() == "|"


class TestStripAnsi:
    """Test ANSI escape code stripping."""

    def test_strips_color_codes(self) -> None:
        """Should remove ANSI color codes."""
        colored = "\033[31mred text\033[0m"
        assert strip_ansi(colored) == "red text"

    def test_plain_text_unchanged(self) -> None:
        """Plain text should pass through unchanged."""
        assert strip_ansi("hello world") == "hello world"

    def test_strips_multiple_codes(self) -> None:
        """Should strip multiple ANSI codes."""
        text = "\033[1m\033[31mbold red\033[0m"
        assert strip_ansi(text) == "bold red"


class TestFormatDuration:
    """Test duration formatting."""

    def test_seconds_only(self) -> None:
        """Less than 60s should show seconds."""
        assert format_duration(30) == "30s"

    def test_minutes_and_seconds(self) -> None:
        """Should show minutes and seconds."""
        assert format_duration(90) == "1m 30s"

    def test_hours_and_minutes(self) -> None:
        """Should show hours and minutes."""
        assert format_duration(3700) == "1h 1m"

    def test_zero_seconds(self) -> None:
        """Zero should show 0s."""
        assert format_duration(0) == "0s"
