"""
Terminal UI styling for BT-7274.
Provides clean, block-character-based output with no emojis.
"""

import shutil


def term_width() -> int:
    """Get terminal width, fallback to 60."""
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return 60


def header(text: str, width: int = None):
    """Print a clean header line."""
    print(f"\n  {text}")


def section(title: str):
    """Print a section divider with title."""
    print(f"\n  {title}")
    print(f"  {'─' * 40}")


def sub_section(title: str):
    """Print a subsection title."""
    print(f"\n  {title}")


def info(msg: str):
    """General info line."""
    print(f"  │  {msg}")


def success(msg: str):
    """Success line."""
    print(f"  │  [OK] {msg}")


def warning(msg: str):
    """Warning line."""
    print(f"  │  [WARN] {msg}")


def error(msg: str):
    """Error line."""
    print(f"  │  [ERR] {msg}")


def status(label: str, msg: str):
    """Status update with label."""
    print(f"  │  [{label}] {msg}")


def bullet(msg: str):
    """Bullet point."""
    print(f"  │    - {msg}")


def spacer():
    """Print a blank spacer line."""
    print("")


def divider():
    """Print a thin divider line."""
    print("─" * term_width())


def footer(text: str = ""):
    """Print a clean footer line."""
    if text:
        print(f"\n  {text}")
    print("")


def prompt(text: str) -> str:
    """Print a prompt and return user input."""
    return input(f"  > {text} ")


def choice_menu(title: str, options: list[str], default: str = None) -> str:
    """
    Display a choice menu and return the selected option string.
    options: list of strings like '1) Option A'.
    """
    section(title)
    for opt in options:
        print(f"  │  {opt}")
    if default:
        return input(f"\n  > Select option (default: {default}): ").strip() or default
    return input("\n  > Select option: ").strip()


def box(title: str, lines: list[str]):
    """Draw a box around content lines."""
    w = max(len(title), max((len(l) for l in lines), default=0)) + 4
    top = f"┌{'─' * (w - 2)}┐"
    mid_title = f"│ {title.ljust(w - 3)}│"
    sep = f"├{'─' * (w - 2)}┤"
    body = "\n".join(f"│ {l.ljust(w - 3)}│" for l in lines)
    bottom = f"└{'─' * (w - 2)}┘"
    print(f"\n{top}\n{mid_title}\n{sep}\n{body}\n{bottom}")


def progress(current: int, total: int, label: str = ""):
    """Print a progress indicator."""
    bar_len = 20
    filled = int(bar_len * current / total) if total else 0
    bar = "█" * filled + "░" * (bar_len - filled)
    pct = f"{current}/{total}"
    print(f"  │  [{bar}] {pct} {label}")


def loading_bar(label: str, current: int = 0, total: int = 10, width: int = 30):
    """Print a loading bar for a task.

    Args:
        label: Description of the task being loaded.
        current: Current progress step.
        total: Total number of steps.
        width: Width of the bar in characters.
    """
    filled = int(width * current / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    pct = int(100 * current / total) if total else 0
    print(f"\r  │  [{bar}] {pct}% {label}", end="", flush=True)
    if current >= total:
        print()  # New line when complete


def quote(speaker: str, text: str):
    """Print a quoted dialogue line."""
    print(f"\n  {speaker}: \"{text}\"")


def log_system(msg: str):
    """System log style line."""
    print(f"  [SYS] {msg}")


def log_stt(msg: str):
    """STT log style line."""
    print(f"  [STT] {msg}")


def log_llm(msg: str):
    """LLM log style line."""
    print(f"  [LLM] {msg}")


def log_tts(msg: str):
    """TTS log style line."""
    print(f"  [TTS] {msg}")


def log_action(msg: str):
    """Action log style line."""
    print(f"  [ACT] {msg}")


def cache_hit(msg: str = "Using cached response"):
    """Cache hit notification."""
    print(f"  [CACHE] {msg}")


def clip_play(phrase: str, source: str = ""):
    """Notify that a voice clip is playing."""
    src = f" ({source})" if source else ""
    print(f"  [CLIP{src}] \"{phrase}\"")


def listening(msg: str = "Listening..."):
    """Listening prompt."""
    print(f"\n  [MIC] {msg}")


def goodbye():
    """Farewell message."""
    print("\n  [SYS] Goodbye, Pilot.\n")
