#!/usr/bin/env python3
"""BT-7274 Voice Assistant - Main Pipeline (backward-compatible wrapper).

This file re-exports BT7274Assistant from the pipeline package for backward
compatibility. New code should import from bt7274_assistant.pipeline directly.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path when run directly (e.g., via bt-link)
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from bt7274_assistant.pipeline.core import BT7274Assistant

__all__ = ["BT7274Assistant"]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="BT-7274 Voice Assistant")
    parser.add_argument("--generate-responses", action="store_true",
                        help="Generate missing standby response audio files")
    parser.add_argument("--force-regenerate", action="store_true",
                        help="Force regenerate ALL standby audio files")
    parser.add_argument("--ai-mode", choices=["local", "cloud"],
                        help="AI mode (local or cloud)")
    parser.add_argument("--performance-mode", choices=["standard", "performance"],
                        help="TTS mode (standard or performance)")
    parser.add_argument("--console-chat-mode", action="store_true",
                        help="Run in console chat mode (text input, no microphone)")
    args = parser.parse_args()

    assistant = BT7274Assistant(
        ai_mode=args.ai_mode,
        performance_mode=args.performance_mode,
        console_chat_mode=args.console_chat_mode,
    )

    if args.generate_responses or args.force_regenerate:
        assistant.initialize()
        count = assistant.generate_standby_responses(force_regenerate=args.force_regenerate)
        from ui import footer
        footer(f"Successfully generated {count} standby responses!")
    else:
        assistant.run()
