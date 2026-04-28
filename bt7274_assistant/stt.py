"""
Speech-to-Text module using OpenAI Whisper.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import whisper
import numpy as np
import soundfile as sf
from scipy import signal
from typing import Tuple
from ui import info, success, warning, error

from bt7274_workstation.session_cache_manager import get_stt_temp_dir


class WhisperSTT:
    def __init__(self, config: dict):
        self.config = config
        self.model_name = config.get("model", "base.en")
        self.device = config.get("device", "cpu")
        self.language = config.get("language", "en")
        self._model = None

    @property
    def model(self):
        """Lazy-load the Whisper model."""
        if self._model is None:
            info(f"Loading Whisper model '{self.model_name}' on {self.device}...")
            self._model = whisper.load_model(self.model_name).to(self.device)
        return self._model

    def transcribe(self, audio_path: str) -> dict:
        """Transcribe an audio file to text.
        
        Returns:
            dict with keys: text (str), confidence (float), language (str)
        """
        try:
            # Preprocess audio for noise reduction if it's a WAV file
            processed_audio_path = audio_path
            if audio_path.endswith('.wav'):
                try:
                    # Load audio and apply noise reduction
                    audio_data, sample_rate = sf.read(audio_path)
                    if len(audio_data.shape) > 1:
                        audio_data = audio_data[:, 0]  # Use only first channel if stereo
                    if len(audio_data) > 0:
                        cleaned_audio = self._reduce_noise(audio_data, sample_rate)
                        
                        # Save processed audio to temporary file in session cache
                        stt_temp = get_stt_temp_dir()
                        processed_audio_path = tempfile.mktemp(suffix=".wav", dir=str(stt_temp))
                        sf.write(processed_audio_path, cleaned_audio, sample_rate)
                except Exception as preprocess_error:
                    # If preprocessing fails, use original audio
                    warning(f"Audio preprocessing failed: {preprocess_error}")
                    processed_audio_path = audio_path
            
            result = self.model.transcribe(
                processed_audio_path,
                language=self.language,
                fp16=False  # M1 doesn't support fp16 well
            ) if self.model else {}
            text_raw = result.get("text", "") if isinstance(result, dict) else ""
            text = text_raw.strip() if isinstance(text_raw, str) else ""
            
            # Calculate confidence from segment probabilities
            segments = result.get("segments", []) if result and isinstance(result, dict) else []
            if segments and isinstance(segments, list):
                avg_logprob = sum(s.get("avg_logprob", 0) if isinstance(s, dict) else 0 for s in segments) / len(segments)
                # Convert logprob to approximate confidence (0-1 scale)
                confidence = min(1.0, max(0.0, 1.0 + avg_logprob)) if isinstance(avg_logprob, (int, float)) else 0.0
            else:
                confidence = 0.0
            
            # Clean up temporary processed file
            if processed_audio_path != audio_path and os.path.exists(processed_audio_path):
                try:
                    os.remove(processed_audio_path)
                except Exception as cleanup_error:
                    warning(f"Failed to clean up temporary file: {cleanup_error}")
            
            return {
                "text": text,
                "confidence": confidence,
                "language": result.get("language", self.language),
            }
        except Exception as e:
            error(f"STT error: {e}")
            # Log error for debugging
            import logging
            logging.error(f"STT Transcription Error: {e}", exc_info=True)
            return {
                "text": "",
                "confidence": 0.0,
                "language": self.language,
                "error": f"STT transcription failed: {str(e)}",
            }

    def _reduce_noise(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Apply noise reduction to audio signal."""
        try:
            # Apply a bandpass filter to remove very low and very high frequencies
            # Keep frequencies between 100Hz and 8000Hz which is where most speech energy is
            low_freq = 100
            high_freq = min(8000, sample_rate // 2 - 100)  # Ensure high_freq is safely less than nyquist
            nyquist = sample_rate / 2
            
            # Ensure frequencies are within valid range for digital filters
            if nyquist > low_freq and nyquist > high_freq and high_freq > low_freq:
                low = max(0.01, low_freq / nyquist)  # Ensure low > 0
                high = min(0.99, high_freq / nyquist)  # Ensure high < 1
                
                # Only apply filter if frequencies are valid and in correct order
                if low < high and low > 0 and high < 1:
                    try:
                        butter_result = signal.butter(4, [low, high], btype='band')
                        if isinstance(butter_result, tuple) and len(butter_result) >= 2:
                            b, a = butter_result[0], butter_result[1]
                            filtered_audio = signal.filtfilt(b, a, audio)
                        else:
                            # If filtering fails, use original audio
                            warning(f"Bandpass filter returned unexpected result: {type(butter_result)}")
                            filtered_audio = audio
                    except Exception as filter_error:
                        # If filtering fails, use original audio
                        warning(f"Bandpass filter failed: {filter_error}")
                        filtered_audio = audio
                else:
                    # Skip filtering if frequencies are invalid
                    filtered_audio = audio
            else:
                # Skip filtering if sample rate is too low
                filtered_audio = audio
                
            # Apply spectral subtraction for additional noise reduction
            # This helps in very noisy environments
            try:
                fft_data = np.fft.rfft(filtered_audio)
                magnitude = np.abs(fft_data)
                phase = np.angle(fft_data)
                
                # Estimate noise floor (10th percentile of magnitude)
                if len(magnitude) > 0:
                    noise_floor = np.percentile(magnitude, 10)
                    
                    # Subtract noise floor with a safety factor
                    spectral_floor = noise_floor * 1.5
                    reduced_magnitude = np.maximum(magnitude - spectral_floor, 0)
                    
                    # Reconstruct signal
                    reduced_fft = reduced_magnitude * np.exp(1j * phase)
                    reduced_audio = np.fft.irfft(reduced_fft)
                    
                    # Normalize to prevent clipping
                    if len(reduced_audio) > 0 and np.max(np.abs(reduced_audio)) > 0:
                        reduced_audio = reduced_audio / np.max(np.abs(reduced_audio)) * 0.9
                    else:
                        reduced_audio = filtered_audio
                else:
                    reduced_audio = filtered_audio
                    
            except Exception as spectral_error:
                # If spectral subtraction fails, use filtered audio
                warning(f"Spectral subtraction failed: {spectral_error}")
                reduced_audio = filtered_audio
                
        except Exception as e:
            # If any noise reduction step fails, return original audio
            warning(f"Noise reduction failed: {e}")
            reduced_audio = audio

        return reduced_audio

    def transcribe_buffer(self, audio_buffer: np.ndarray, sample_rate: int = 16000) -> dict:
        """Transcribe from an in-memory audio buffer."""
        try:
            # Apply noise reduction for better performance in noisy environments
            if len(audio_buffer) > 0:
                cleaned_audio = self._reduce_noise(audio_buffer, sample_rate)
            else:
                cleaned_audio = audio_buffer
            
            stt_temp = get_stt_temp_dir()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=str(stt_temp)) as f:
                sf.write(f.name, cleaned_audio, sample_rate)
                result = self.transcribe(f.name)
                try:
                    os.remove(f.name)
                except Exception as cleanup_error:
                    warning(f"Failed to clean up temporary file: {cleanup_error}")
            return result
        except Exception as e:
            return {
                "text": "",
                "confidence": 0.0,
                "language": self.language,
                "error": f"STT buffer transcription failed: {str(e)}",
            }

    def unload(self):
        """Free model from memory."""
        self._model = None
        import gc
        gc.collect()
