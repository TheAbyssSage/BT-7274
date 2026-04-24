#!/usr/bin/env python3
"""
Test script for BT-7274 noise improvements.
"""

import numpy as np
import soundfile as sf
import tempfile
import os
from bt7274_assistant.stt import WhisperSTT

def create_test_audio_with_noise():
    """Create a test audio file with simulated noise."""
    # Generate a simple sine wave as "speech"
    duration = 3.0  # seconds
    sample_rate = 16000
    frequency = 440  # Hz
    
    # Time array
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    
    # Generate sine wave (our "speech")
    speech = np.sin(2 * np.pi * frequency * t) * 0.5
    
    # Add noise
    noise_amplitude = 0.1  # Adjust to simulate different noise levels
    noise = np.random.normal(0, noise_amplitude, len(speech))
    
    # Combine speech and noise
    noisy_audio = speech + noise
    
    # Normalize to prevent clipping
    noisy_audio = noisy_audio / np.max(np.abs(noisy_audio)) * 0.9
    
    # Save to temporary file
    temp_path = tempfile.mktemp(suffix=".wav")
    sf.write(temp_path, noisy_audio, sample_rate)
    
    return temp_path

def test_noise_reduction():
    """Test the noise reduction functionality."""
    print("Testing noise reduction improvements...")
    
    # Create test audio with noise
    test_audio_path = create_test_audio_with_noise()
    print(f"Created test audio with noise: {test_audio_path}")
    
    # Initialize STT
    config = {
        "model": "base.en",
        "language": "en",
        "device": "cpu"
    }
    stt = WhisperSTT(config)
    
    # Test transcription with noise reduction
    print("Transcribing with noise reduction...")
    result = stt.transcribe(test_audio_path)
    
    print(f"Transcription result:")
    print(f"  Text: '{result.get('text', 'N/A')}'")
    print(f"  Confidence: {result.get('confidence', 0.0):.2f}")
    
    # Clean up
    os.remove(test_audio_path)
    
    return result

if __name__ == "__main__":
    result = test_noise_reduction()
    print("\nNoise reduction test completed.")