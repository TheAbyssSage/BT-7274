"""Benchmark BT-7274 response time for common queries."""
import time
from bt7274_assistant.pipeline.core import BT7274Assistant


def main():
    print("Initializing BT-7274 (one-time)...")
    start = time.time()
    assistant = BT7274Assistant(
        ai_mode="local",
        performance_mode="standard",
        console_chat_mode=True,
    )
    assistant.initialize()
    startup_time = time.time() - start
    print(f"Startup time: {startup_time:.1f}s")
    assert startup_time < 45, f"Startup took {startup_time:.1f}s, expected < 45s"

    # Test 1: Gratitude (should be instant - no LLM call)
    print("\n--- Test: Gratitude ---")
    start = time.time()
    assistant.process_command(
        audio_path=None,
        skip_wake_word=True,
        pre_transcribed_text="Thank you BT",
    )
    elapsed = time.time() - start
    print(f"Gratitude response time: {elapsed:.1f}s")
    assert elapsed < 5.0, f"Gratitude took {elapsed:.1f}s, expected < 5s"

    # Test 2: Time query (action handler, no LLM)
    print("\n--- Test: Time query ---")
    start = time.time()
    assistant.process_command(
        audio_path=None,
        skip_wake_word=True,
        pre_transcribed_text="BT what time is it",
    )
    elapsed = time.time() - start
    print(f"Time query response time: {elapsed:.1f}s")
    assert elapsed < 25.0, f"Time query took {elapsed:.1f}s, expected < 25s"

    # Test 3: Location query (action handler, no LLM)
    print("\n--- Test: Location query ---")
    start = time.time()
    assistant.process_command(
        audio_path=None,
        skip_wake_word=True,
        pre_transcribed_text="BT where am I",
    )
    elapsed = time.time() - start
    print(f"Location query response time: {elapsed:.1f}s")
    assert elapsed < 25.0, f"Location query took {elapsed:.1f}s, expected < 25s"

    print("\nAll speed benchmarks passed!")


if __name__ == "__main__":
    main()
