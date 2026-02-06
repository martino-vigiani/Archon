"""
CLI Display Components for Archon.

Single source of truth for all terminal output:
- ANSI color system with TTY detection
- Terminal personality badges and status indicators
- Quality gradient visualization
- Organic flow state display
- Contract and intervention display
- Box drawing and table utilities
- Progress spinners
"""

import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


# =============================================================================
# Color System - Single Source of Truth
# =============================================================================


class Colors:
    """ANSI color codes for terminal output.

    This is the ONLY place colors should be defined. All other modules
    must import from here.
    """

    RESET = "\033[0m"

    # Styles
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    STRIKETHROUGH = "\033[9m"

    # Standard colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background colors
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"

    @classmethod
    def disable(cls) -> None:
        """Disable colors for non-TTY output (piped, CI environments)."""
        for attr in dir(cls):
            if attr.isupper() and not attr.startswith("_"):
                setattr(cls, attr, "")


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


def c(text: str, *colors: str) -> str:
    """Apply colors to text."""
    if not colors:
        return text
    return "".join(colors) + text + Colors.RESET


# =============================================================================
# Terminal Personalities
# =============================================================================


@dataclass
class TerminalPersonality:
    """Terminal personality definition."""

    id: str
    name: str
    emoji: str
    color: str
    description: str


TERMINAL_PERSONALITIES: dict[str, TerminalPersonality] = {
    "t1": TerminalPersonality(
        id="t1",
        name="Craftsman",
        emoji="*",  # Represents craftsmanship star
        color=Colors.BRIGHT_CYAN,
        description="Every pixel matters",
    ),
    "t2": TerminalPersonality(
        id="t2",
        name="Architect",
        emoji="#",  # Represents structure
        color=Colors.BRIGHT_MAGENTA,
        description="Foundation that endures",
    ),
    "t3": TerminalPersonality(
        id="t3",
        name="Narrator",
        emoji=">",  # Represents storytelling
        color=Colors.BRIGHT_YELLOW,
        description="Clarity illuminates",
    ),
    "t4": TerminalPersonality(
        id="t4",
        name="Strategist",
        emoji="@",  # Represents vision
        color=Colors.BRIGHT_BLUE,
        description="Vision guides direction",
    ),
    "t5": TerminalPersonality(
        id="t5",
        name="Skeptic",
        emoji="?",  # Represents questioning
        color=Colors.BRIGHT_RED,
        description="Trust but verify",
    ),
}


def get_terminal_badge(terminal_id: str, include_name: bool = True) -> str:
    """Get a colored badge for a terminal."""
    personality = TERMINAL_PERSONALITIES.get(terminal_id)
    if not personality:
        return f"[{terminal_id.upper()}]"

    badge = f"[{terminal_id.upper()}]"
    if include_name:
        badge = f"[{terminal_id.upper()} {personality.name}]"

    return c(badge, personality.color)


# =============================================================================
# Quality Gradient Display
# =============================================================================


def quality_bar(quality: float, width: int = 10) -> str:
    """
    Create a visual quality bar using block characters.

    Args:
        quality: Quality level 0.0 to 1.0
        width: Width in characters

    Returns:
        Colored progress bar string
    """
    quality = max(0.0, min(1.0, quality))  # Clamp to 0-1
    filled = int(quality * width)
    empty = width - filled

    # Color based on quality level
    if quality >= 0.8:
        bar_color = Colors.BRIGHT_GREEN
    elif quality >= 0.6:
        bar_color = Colors.BRIGHT_CYAN
    elif quality >= 0.4:
        bar_color = Colors.BRIGHT_YELLOW
    else:
        bar_color = Colors.BRIGHT_RED

    bar = c("=" * filled, bar_color) + c("-" * empty, Colors.DIM)
    return f"[{bar}]"


def quality_label(quality: float) -> str:
    """Get a descriptive label for a quality level."""
    if quality >= 0.95:
        return c("Excellent", Colors.BRIGHT_GREEN, Colors.BOLD)
    elif quality >= 0.8:
        return c("Polished", Colors.BRIGHT_GREEN)
    elif quality >= 0.6:
        return c("Solid", Colors.BRIGHT_CYAN)
    elif quality >= 0.4:
        return c("Working", Colors.BRIGHT_YELLOW)
    elif quality >= 0.2:
        return c("Draft", Colors.YELLOW)
    else:
        return c("Starting", Colors.DIM)


# =============================================================================
# Flow State Display
# =============================================================================


FlowState = Literal["idle", "flowing", "blocked", "syncing", "completing"]


def flow_state_indicator(state: FlowState) -> str:
    """Get a visual indicator for flow state."""
    indicators = {
        "idle": c("~", Colors.DIM),
        "flowing": c(">>", Colors.BRIGHT_GREEN),
        "blocked": c("!!", Colors.BRIGHT_RED),
        "syncing": c("<>", Colors.BRIGHT_YELLOW),
        "completing": c("OK", Colors.BRIGHT_GREEN, Colors.BOLD),
    }
    return indicators.get(state, c("?", Colors.DIM))


# =============================================================================
# Organic Banner
# =============================================================================


def print_organic_banner() -> None:
    """Print the organic flow banner with terminal personalities."""
    # ASCII art for ARCHON
    banner_lines = [
        "",
        c("    ╔═══════════════════════════════════════════════════════════════╗", Colors.BRIGHT_CYAN),
        c("    ║", Colors.BRIGHT_CYAN) + "                                                               " + c("║", Colors.BRIGHT_CYAN),
        c("    ║", Colors.BRIGHT_CYAN) + c("     █████╗ ██████╗  ██████╗██╗  ██╗ ██████╗ ███╗   ██╗", Colors.BRIGHT_MAGENTA) + "       " + c("║", Colors.BRIGHT_CYAN),
        c("    ║", Colors.BRIGHT_CYAN) + c("    ██╔══██╗██╔══██╗██╔════╝██║  ██║██╔═══██╗████╗  ██║", Colors.BRIGHT_MAGENTA) + "       " + c("║", Colors.BRIGHT_CYAN),
        c("    ║", Colors.BRIGHT_CYAN) + c("    ███████║██████╔╝██║     ███████║██║   ██║██╔██╗ ██║", Colors.BRIGHT_BLUE) + "       " + c("║", Colors.BRIGHT_CYAN),
        c("    ║", Colors.BRIGHT_CYAN) + c("    ██╔══██║██╔══██╗██║     ██╔══██║██║   ██║██║╚██╗██║", Colors.BRIGHT_BLUE) + "       " + c("║", Colors.BRIGHT_CYAN),
        c("    ║", Colors.BRIGHT_CYAN) + c("    ██║  ██║██║  ██║╚██████╗██║  ██║╚██████╔╝██║ ╚████║", Colors.CYAN) + "       " + c("║", Colors.BRIGHT_CYAN),
        c("    ║", Colors.BRIGHT_CYAN) + c("    ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝", Colors.CYAN) + "       " + c("║", Colors.BRIGHT_CYAN),
        c("    ║", Colors.BRIGHT_CYAN) + "                                                               " + c("║", Colors.BRIGHT_CYAN),
        c("    ║", Colors.BRIGHT_CYAN) + c("            Organic Multi-Agent Orchestrator", Colors.BRIGHT_WHITE, Colors.BOLD) + "                 " + c("║", Colors.BRIGHT_CYAN),
        c("    ║", Colors.BRIGHT_CYAN) + c("              Work flows. Quality emerges.", Colors.DIM) + "                    " + c("║", Colors.BRIGHT_CYAN),
        c("    ║", Colors.BRIGHT_CYAN) + "                                                               " + c("║", Colors.BRIGHT_CYAN),
        c("    ╚═══════════════════════════════════════════════════════════════╝", Colors.BRIGHT_CYAN),
        "",
    ]

    for line in banner_lines:
        print(line)


def print_terminals_ready(terminals: list[str] | None = None) -> None:
    """Print the terminals ready status with personalities."""
    if terminals is None:
        terminals = ["t1", "t2", "t3", "t4", "t5"]

    print(c("    Terminals Ready:", Colors.BOLD, Colors.WHITE))
    print()

    for tid in terminals:
        personality = TERMINAL_PERSONALITIES.get(tid)
        if personality:
            badge = c(f"    [{tid.upper()}]", personality.color)
            name = c(personality.name, personality.color, Colors.BOLD)
            desc = c(f'"{personality.description}"', Colors.DIM)
            print(f"{badge} {name} - {desc}")

    print()


# =============================================================================
# Organic Status Display
# =============================================================================


@dataclass
class TerminalStatus:
    """Status of a single terminal."""

    terminal_id: str
    quality: float  # 0.0 to 1.0
    current_work: str
    flow_state: FlowState


def print_organic_status(
    terminals: list[TerminalStatus],
    active_contracts: int = 0,
    interventions: int = 0,
    elapsed_seconds: float = 0,
) -> None:
    """
    Print a beautiful organic status display.

    Example output:
    ╭─────────────────────────────────────────────╮
    │ ARCHON - Organic Flow Active                │
    ├─────────────────────────────────────────────┤
    │ T1 Craftsman  [########--] 0.78 UI Layout   │
    │ T2 Architect  [######----] 0.62 Data Layer  │
    │ T3 Narrator   [####------] 0.41 README      │
    │ T4 Strategist [##########] 0.95 Scope Done  │
    │ T5 Skeptic    [##--------] 0.23 Testing...  │
    ├─────────────────────────────────────────────┤
    │ Active Contracts: 3  │  Interventions: 2    │
    ╰─────────────────────────────────────────────╯
    """
    width = 55
    inner_width = width - 4  # Account for borders and padding

    # Format elapsed time
    minutes = int(elapsed_seconds // 60)
    seconds = int(elapsed_seconds % 60)
    time_str = f"{minutes:02d}:{seconds:02d}"

    # Top border
    print(c("    ╭" + "─" * (width - 2) + "╮", Colors.BRIGHT_CYAN))

    # Header
    header = f" ARCHON - Organic Flow Active"
    header_padding = " " * (inner_width - len(header) - len(time_str))
    print(c("    │", Colors.BRIGHT_CYAN) + c(header, Colors.BRIGHT_WHITE, Colors.BOLD) + header_padding + c(time_str, Colors.DIM) + c(" │", Colors.BRIGHT_CYAN))

    # Separator
    print(c("    ├" + "─" * (width - 2) + "┤", Colors.BRIGHT_CYAN))

    # Terminal rows
    for status in terminals:
        personality = TERMINAL_PERSONALITIES.get(status.terminal_id)
        if not personality:
            continue

        # Build the row
        tid = status.terminal_id.upper()
        name = personality.name.ljust(10)
        qbar = quality_bar(status.quality, 10)
        qval = f"{status.quality:.2f}"
        work = status.current_work[:15].ljust(15)

        # Color the terminal name
        colored_name = c(name, personality.color)

        row = f" {tid} {colored_name} {qbar} {qval} {work}"

        # Calculate actual display length (without ANSI codes)
        # This is approximate since ANSI codes are variable length
        display_len = len(f" {tid} {name} [          ] {qval} {work}")
        padding = " " * max(0, inner_width - display_len)

        print(c("    │", Colors.BRIGHT_CYAN) + row + padding + c("│", Colors.BRIGHT_CYAN))

    # Separator
    print(c("    ├" + "─" * (width - 2) + "┤", Colors.BRIGHT_CYAN))

    # Footer with stats
    contracts_str = f"Contracts: {active_contracts}"
    interventions_str = f"Interventions: {interventions}"
    footer = f" {contracts_str}  |  {interventions_str}"
    footer_padding = " " * (inner_width - len(footer))

    print(c("    │", Colors.BRIGHT_CYAN) + c(footer, Colors.DIM) + footer_padding + c("│", Colors.BRIGHT_CYAN))

    # Bottom border
    print(c("    ╰" + "─" * (width - 2) + "╯", Colors.BRIGHT_CYAN))
    print()


# =============================================================================
# Contract Display
# =============================================================================


@dataclass
class ContractDisplay:
    """Contract information for display."""

    name: str
    defined_by: str
    status: str  # "proposed", "implemented", "verified"
    implemented_by: str | None = None


def print_contracts_summary(contracts: list[ContractDisplay]) -> None:
    """Print a summary of active contracts."""
    if not contracts:
        print(c("    No active contracts.", Colors.DIM))
        return

    print(c("    Active Contracts:", Colors.BOLD, Colors.WHITE))
    print()

    status_colors = {
        "proposed": Colors.BRIGHT_YELLOW,
        "implemented": Colors.BRIGHT_CYAN,
        "verified": Colors.BRIGHT_GREEN,
    }

    status_icons = {
        "proposed": "[?]",
        "implemented": "[>]",
        "verified": "[+]",
    }

    for contract in contracts:
        color = status_colors.get(contract.status, Colors.DIM)
        icon = status_icons.get(contract.status, "[ ]")

        defined_badge = get_terminal_badge(contract.defined_by, include_name=False)
        impl_str = ""
        if contract.implemented_by:
            impl_badge = get_terminal_badge(contract.implemented_by, include_name=False)
            impl_str = f" -> {impl_badge}"

        print(f"    {c(icon, color)} {c(contract.name, Colors.WHITE)} {defined_badge}{impl_str}")

    print()


# =============================================================================
# Intervention Types
# =============================================================================


InterventionType = Literal[
    "AMPLIFY",      # Boost priority of good work
    "REDIRECT",     # Change direction of terminal
    "BRIDGE",       # Connect two terminals
    "CLARIFY",      # Request clarification
    "ACCELERATE",   # Speed up slow progress
    "PAUSE",        # Temporarily pause work
]


def intervention_color(intervention_type: InterventionType) -> str:
    """Get color for intervention type."""
    colors = {
        "AMPLIFY": Colors.BRIGHT_GREEN,
        "REDIRECT": Colors.BRIGHT_YELLOW,
        "BRIDGE": Colors.BRIGHT_CYAN,
        "CLARIFY": Colors.BRIGHT_BLUE,
        "ACCELERATE": Colors.BRIGHT_MAGENTA,
        "PAUSE": Colors.BRIGHT_RED,
    }
    return colors.get(intervention_type, Colors.WHITE)


def print_intervention_help() -> None:
    """Print help for intervention commands."""
    print(c("    Available Interventions:", Colors.BOLD, Colors.WHITE))
    print()

    interventions = [
        ("AMPLIFY", "Boost priority of promising work", "intervene AMPLIFY t1"),
        ("REDIRECT", "Change direction of a terminal", "intervene REDIRECT t2 'Focus on API'"),
        ("BRIDGE", "Connect two terminals' work", "intervene BRIDGE t1 t2"),
        ("CLARIFY", "Request clarification from terminal", "intervene CLARIFY t3"),
        ("ACCELERATE", "Speed up slow progress", "intervene ACCELERATE t2"),
        ("PAUSE", "Temporarily pause terminal", "intervene PAUSE t4"),
    ]

    for name, desc, example in interventions:
        color = intervention_color(name)  # type: ignore
        print(f"    {c(name.ljust(12), color, Colors.BOLD)} {desc}")
        print(f"                     {c(f'Example: {example}', Colors.DIM)}")

    print()


# =============================================================================
# Flow Display
# =============================================================================


def print_flow_state(
    overall_state: FlowState,
    terminals_flowing: list[str],
    terminals_blocked: list[str],
    sync_point_pending: bool = False,
) -> None:
    """Print the current flow state."""
    print(c("    Flow State:", Colors.BOLD, Colors.WHITE))
    print()

    # Overall indicator
    indicator = flow_state_indicator(overall_state)
    state_label = overall_state.upper()

    if overall_state == "flowing":
        state_color = Colors.BRIGHT_GREEN
    elif overall_state == "blocked":
        state_color = Colors.BRIGHT_RED
    elif overall_state == "syncing":
        state_color = Colors.BRIGHT_YELLOW
    else:
        state_color = Colors.DIM

    print(f"    Overall: {indicator} {c(state_label, state_color, Colors.BOLD)}")
    print()

    if terminals_flowing:
        flowing_badges = " ".join(get_terminal_badge(t, include_name=False) for t in terminals_flowing)
        print(f"    {c('Flowing:', Colors.BRIGHT_GREEN)} {flowing_badges}")

    if terminals_blocked:
        blocked_badges = " ".join(get_terminal_badge(t, include_name=False) for t in terminals_blocked)
        print(f"    {c('Blocked:', Colors.BRIGHT_RED)} {blocked_badges}")

    if sync_point_pending:
        print(f"    {c('Sync point pending...', Colors.BRIGHT_YELLOW)}")

    print()


# =============================================================================
# Progress Spinner
# =============================================================================


class Spinner:
    """Spinner for showing activity in the terminal."""

    FRAMES = ["|", "/", "-", "\\"]

    def __init__(self) -> None:
        self._frame = 0

    def next_frame(self) -> str:
        """Get the next spinner frame."""
        frame = self.FRAMES[self._frame]
        self._frame = (self._frame + 1) % len(self.FRAMES)
        return frame


# =============================================================================
# Utility Functions
# =============================================================================


def clear_line() -> None:
    """Clear the current line (for updating in place)."""
    print("\r\033[K", end="")


def move_up(lines: int = 1) -> None:
    """Move cursor up N lines."""
    print(f"\033[{lines}A", end="")


def hide_cursor() -> None:
    """Hide the cursor."""
    print("\033[?25l", end="")


def show_cursor() -> None:
    """Show the cursor."""
    print("\033[?25h", end="")


def strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text for length calculation."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


# =============================================================================
# Box Drawing Utilities
# =============================================================================


def print_box(
    lines: list[str],
    width: int = 55,
    title: str = "",
    border_color: str = Colors.BRIGHT_CYAN,
    indent: int = 4,
) -> None:
    """Print content inside a box with Unicode borders.

    Args:
        lines: Content lines to display inside the box.
        width: Total width of the box including borders.
        title: Optional title to display in the top border.
        border_color: ANSI color for the border.
        indent: Left indentation in spaces.
    """
    pad = " " * indent
    inner = width - 2  # space inside borders

    # Top border
    if title:
        title_stripped = strip_ansi(title)
        remaining = inner - len(title_stripped) - 2  # 2 for spaces around title
        left_border = "─" * 1
        right_border = "─" * max(0, remaining - 1)
        print(c(f"{pad}╭{left_border}", border_color) + f" {title} " + c(f"{right_border}╮", border_color))
    else:
        print(c(f"{pad}╭{'─' * inner}╮", border_color))

    # Content lines
    for line in lines:
        visible_len = len(strip_ansi(line))
        line_padding = " " * max(0, inner - visible_len - 1)
        print(c(f"{pad}│", border_color) + f" {line}{line_padding}" + c("│", border_color))

    # Bottom border
    print(c(f"{pad}╰{'─' * inner}╯", border_color))


def print_separator(
    char: str = "─",
    width: int = 60,
    color: str = Colors.DIM,
    indent: int = 4,
) -> None:
    """Print a horizontal separator line."""
    print(c(f"{' ' * indent}{char * width}", color))


def format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = int(minutes // 60)
    mins = minutes % 60
    return f"{hours}h {mins}m"


def get_terminal_name(terminal_id: str) -> str:
    """Get the display name for a terminal from TERMINAL_PERSONALITIES.

    This is the single source of truth -- never hardcode terminal names elsewhere.
    """
    personality = TERMINAL_PERSONALITIES.get(terminal_id)
    if personality:
        return personality.name
    return terminal_id.upper()


def get_terminal_color(terminal_id: str) -> str:
    """Get the ANSI color for a terminal from TERMINAL_PERSONALITIES.

    This is the single source of truth -- never hardcode terminal colors elsewhere.
    """
    personality = TERMINAL_PERSONALITIES.get(terminal_id)
    if personality:
        return personality.color
    return Colors.WHITE
