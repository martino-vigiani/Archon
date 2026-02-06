"""
Archon Orchestrator - Organic multi-agent coordination system.

This package provides orchestration for 5 parallel Claude Code terminals,
each with a distinct personality, working through organic flow.
"""

__version__ = "2.0.0"
__author__ = "Archon"

from .orchestrator import Orchestrator
from .config import Config, TerminalConfig
from .report_manager import ReportManager, Report

__all__ = ["Orchestrator", "Config", "TerminalConfig", "ReportManager", "Report"]
