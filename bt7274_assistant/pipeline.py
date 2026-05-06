#!/usr/bin/env python3
"""BT-7274 Voice Assistant - Main Pipeline (backward-compatible wrapper).

This file re-exports BT7274Assistant from the pipeline package for backward
compatibility. New code should import from bt7274_assistant.pipeline directly.
"""

from bt7274_assistant.pipeline.core import BT7274Assistant

__all__ = ["BT7274Assistant"]
