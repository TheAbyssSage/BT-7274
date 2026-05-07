"""Benchmark BT-7274 response time for common queries."""
import os
import time
from bt7274_assistant.pipeline.core import BT7274Assistant


def main():
    print("Initializing BT-7274 with Piper TTS (one-time)...")
    start = time.time()
    assistant = BT7274Assistant(
        ai_mode="local",
        performance_mode="standard",
        console_chat_mode=True,
        tts_engine="piper",
    )
    assistant.initialize()
    startup_time = time.time() - start
    print(f"Startup time: {startup_time:.1f}s")
    assert startup_time < 20, f"Startup took {startup_time:.1f}s, expected < 20s (Piper has no model load)"

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
    assert elapsed < 3.5, f"Gratitude took {elapsed:.1f}s, expected < 3.5s"

    # Test 2: Time query (action handler, TTS only)
    print("\n--- Test: Time query ---")
    start = time.time()
    assistant.process_command(
        audio_path=None,
        skip_wake_word=True,
        pre_transcribed_text="BT what time is it",
    )
    elapsed = time.time() - start
    print(f"Time query response time: {elapsed:.1f}s")
    assert elapsed < 10.0, f"Time query took {elapsed:.1f}s, expected < 10s (includes audio playback)"

    # Test 3: Location query (action handler, TTS only)
    print("\n--- Test: Location query ---")
    start = time.time()
    assistant.process_command(
        audio_path=None,
        skip_wake_word=True,
        pre_transcribed_text="BT where am I",
    )
    elapsed = time.time() - start
    print(f"Location query response time: {elapsed:.1f}s")
    assert elapsed < 10.0, f"Location query took {elapsed:.1f}s, expected < 10s (includes audio playback)"

    # Test 4: Piper standalone synthesis speed
    print("\n--- Test: Piper standalone speed ---")
    from bt7274_assistant.tts_piper import FastPiperTTS
    piper = FastPiperTTS({})
    texts = [
        "Ready.",
        "Copy that, Pilot. Standing by for orders.",
        "Pilot, the current time is 06:23 PM. Today is Thursday, May 07, 2026. All systems operational.",
    ]
    for text in texts:
        start = time.time()
        path = piper.speak(text)
        elapsed = time.time() - start
        print(f"  {len(text)} chars: {elapsed:.3f}s")
        assert elapsed < 1.0, f"Piper took {elapsed:.3f}s for {len(text)} chars, expected < 1s"
        assert path and os.path.exists(path), f"No output file for: {text}"

    print("\nAll speed benchmarks passed!")


if __name__ == "__main__":
    main()
