"""
Archon Orchestrator - Multi-terminal Claude Code coordination system.

This package provides orchestration for 4 parallel Claude Code terminals,
each specialized for different aspects of software development.
"""

__version__ = "0.1.0"
__author__ = "Archon"

from .orchestrator import Orchestrator
from .config import Config, TerminalConfig
from .report_manager import ReportManager, Report

__all__ = ["Orchestrator", "Config", "TerminalConfig", "ReportManager", "Report"]
