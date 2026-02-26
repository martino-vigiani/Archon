"""
Archon Orchestrator - Organic multi-agent coordination system.

This package provides orchestration for 5 parallel Claude Code terminals,
each with a distinct personality, working through organic flow.
"""

__version__ = "2.0.0"
__author__ = "Archon"

from .config import Config, TerminalConfig
from .orchestrator import Orchestrator
from .report_manager import Report, ReportManager

__all__ = ["Orchestrator", "Config", "TerminalConfig", "ReportManager", "Report"]
