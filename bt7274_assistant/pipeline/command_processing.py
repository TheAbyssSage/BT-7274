"""The main process_command method and its helpers."""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from ui import (
    quote, status, info, error, warning, log_stt, log_llm, log_tts, log_action,
    cache_hit, clip_play, listening, goodbye
)
from utils import play_audio, record_until_silence

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SEMANTIC_SIMILARITY_AVAILABLE = True
except ImportError:
    SEMANTIC_SIMILARITY_AVAILABLE = False

logger = logging.getLogger("BT7274")


class CommandProcessingMixin:
    """Mixin containing the main process_command method and follow-up listener."""

    def generate_standby_responses(self, force_regenerate: bool = False):
        """Generate standby response audio files using BT's voice.
        
        Args:
            force_regenerate: If True, regenerate all clips even if they exist.
        """
        section("Generating standby responses with BT's voice")
        
        # Collect all phrases from config
        all_phrases = []
        pipeline = self.config.get("pipeline", {})
        for key in pipeline:
            if key.startswith("standby_phrases"):
                all_phrases.extend(pipeline[key])
        
        # Add common response patterns for better caching coverage
        common_responses = [
            "Processing complete, Pilot.",
            "Operation complete, Pilot.",
            "Task completed, Pilot.",
            "Execution successful, Pilot.",
            "Sequence complete, Pilot.",
            "Protocol fulfilled, Pilot.",
            "Mission accomplished, Pilot.",
            "Objective achieved, Pilot."
        ]
        all_phrases.extend(common_responses)
        
        # Remove duplicates while preserving order
        seen = set()
        phrases = []
        for p in all_phrases:
            if p not in seen:
                seen.add(p)
                phrases.append(p)
        
        generated_count = 0
        skipped_count = 0
        output_dir = Path(__file__).parent / "standby"
        output_dir.mkdir(exist_ok=True)
        
        for phrase in phrases:
            # Create safe filename
            safe_name = "".join(c if c.isalnum() or c in [' ', '-'] else "_" for c in phrase.lower())
            safe_name = safe_name.replace(" ", "_").replace("-", "_")
            
            # Check recursively for existing file
            found_paths = list(output_dir.rglob(f"{safe_name}.wav"))
            output_path = found_paths[0] if found_paths else output_dir / f"{safe_name}.wav"
            
            if found_paths and not force_regenerate:
                info(f"Skipping: {phrase}")
                skipped_count += 1
                continue
                
            info(f"Generating: {phrase}")
            try:
                # Remove old file if forcing regeneration
                if output_path.exists() and force_regenerate:
                    output_path.unlink()
                    
                wav_path = self.tts.speak(phrase) if self.tts else None
                if wav_path:
                    import shutil
                    shutil.move(wav_path, str(output_path))
                    success(f"Saved: {output_path.name}")
                    generated_count += 1
                else:
                    error(f"Failed: {phrase}")
            except Exception as e:
                error(f"Error generating '{phrase}': {e}")
        
        footer(f"Done! Generated: {generated_count}, Skipped: {skipped_count}")
        return generated_count

    def process_command(self, audio_path: Optional[str] = None, skip_wake_word: bool = False, follow_up_depth: int = 0, pre_transcribed_text: Optional[str] = None) -> bool:
        """Process a single voice command."""
        if audio_path is None and pre_transcribed_text is None:
            raise ValueError("Either audio_path or pre_transcribed_text must be provided")

        # 1. Speech-to-Text
        stt_confidence = None
        if pre_transcribed_text is not None:
            text = pre_transcribed_text
            quote("Pilot", text)
        else:
            log_stt("Transcribing...")
            try:
                if audio_path is None:
                    raise ValueError("audio_path is required when pre_transcribed_text is not provided")
                stt_result = self.stt.transcribe(audio_path) if self.stt else {"text": "", "confidence": 0.0}
                text = stt_result.get("text", "") if isinstance(stt_result, dict) else str(stt_result)
                stt_confidence = stt_result.get("confidence") if isinstance(stt_result, dict) else None
            except Exception as e:
                self._report_error("stt", "transcribe", e, {"audio_path": audio_path})
                text = ""
                stt_confidence = 0.0
            if not text or not text.strip():
                error("No speech detected.")
                return False
            quote("Pilot", text)
            
            # Confidence-based filtering for noisy environments
            min_confidence = self.config["stt"].get("min_confidence", 0.3)
            if stt_confidence is not None and stt_confidence < min_confidence:
                warning(f"Low confidence transcription ({stt_confidence:.2f}). Treating as noise.")
                # Log rejected utterance for debugging
                try:
                    self.logger.log_interaction(
                        pilot_message=text,
                        bt_response="[REJECTED - low confidence]",
                        interaction_type="voice_rejected",
                        ai_mode=self.ai_mode,
                        performance_mode=self.performance_mode or "standard",
                        stt_confidence=stt_confidence,
                        audio_file_path=audio_path,
                        session_id=self.session_id,
                        protocol_reference="Protocol 3: Protect the Pilot",
                        pilot_trust_level=self.pilot_trust_level,
                        metadata={"rejection_reason": "low_confidence", "min_confidence": min_confidence}
                    )
                except Exception:
                    pass
                return False

        # Check wake words
        if not skip_wake_word:
            wake_words = self.config["pipeline"].get("wake_words", [])
            if wake_words and not any(ww.lower() in text.lower() for ww in wake_words):
                info("Wake word not detected. Ignoring.")
                return False

        # Helper: speak a standby phrase immediately (pre-recorded if available)
        def speak_standby(task: str = "generic"):
            task_key = f"standby_phrases_{task}"
            phrases = self.config["pipeline"].get(task_key) or self.config["pipeline"].get("standby_phrases", ["Copy that, Pilot. Stand by."])
            import random
            
            # Update personality weights based on current context
            current_topic = self.current_context.get("topic", "neutral")
            self._update_personality_weights(current_topic)
            
            # Apply personality-based weighting to phrases
            weighted_phrases = self._apply_personality_weights(phrases, " ".join(phrases))
            
            # Try context-aware phrase selection first
            context_phrases = self._get_context_aware_phrases()
            if context_phrases:
                # Filter to only phrases that are in our standby phrases and context-aware
                matching_phrases = [p for p in phrases if self._normalize_phrase(p) in context_phrases]
                if matching_phrases:
                    # Apply personality weighting to context matches
                    weighted_context = self._apply_personality_weights(matching_phrases, " ".join(matching_phrases))
                    if weighted_context:
                        phrase = weighted_context[0][0]  # Take highest weighted
                        status("STBY", f"[Context+Personality] {phrase}")
                    else:
                        phrase = random.choice(matching_phrases)
                        status("STBY", f"[Context-aware] {phrase}")
                else:
                    if weighted_phrases:
                        phrase = weighted_phrases[0][0]  # Take highest weighted
                        status("STBY", f"[Personality] {phrase}")
                    else:
                        phrase = random.choice(phrases)
                        status("STBY", phrase)
            else:
                if weighted_phrases:
                    phrase = weighted_phrases[0][0]  # Take highest weighted
                    status("STBY", f"[Personality] {phrase}")
                else:
                    phrase = random.choice(phrases)
                    status("STBY", phrase)

            # Try pre-recorded clip first (BT's original clips take priority)
            key = self._normalize_phrase(phrase)
            wav_path = self.bt_clips.get(key) or self.standby_clips.get(key)
            if wav_path and Path(wav_path).exists():
                play_audio(wav_path)
                return

            # Fallback: generate on the fly
            if self.tts:
                wav = self.tts.speak(phrase)
                if wav:
                    play_audio(wav)
                
        # Helper: try to find a suitable standby clip for common responses
        def try_standby_for_response(response_text: str) -> Optional[str]:
            """Try to match a response to a pre-generated standby clip with enhanced matching."""
            if not response_text:
                return None
                
            normalized = self._normalize_phrase(response_text)
            
            # 1. First, try dynamic clip selection (combines all matching methods)
            dynamic_clip = self._select_dynamic_clip(response_text)
            if dynamic_clip and Path(dynamic_clip).exists():
                return dynamic_clip
            
            # 2. Check for exact BT clip match
            if normalized in self.bt_clips:
                return self.bt_clips[normalized]
            
            # 3. Check for exact standby clip match
            if normalized in self.standby_clips:
                return self.standby_clips[normalized]
                
            # 4. Try fuzzy matching for BT clips (partial matches)
            for key, path in self.bt_clips.items():
                if normalized in key or key in normalized:
                    if Path(path).exists():
                        return path
            
            # 5. Try semantic similarity matching if available
            if self.semantic_vectorizer and self.semantic_clip_matrix is not None:
                try:
                    response_vector = self.semantic_vectorizer.transform([normalized])
                    similarities = cosine_similarity(response_vector, self.semantic_clip_matrix)
                    best_match_idx = np.argmax(similarities)
                    best_similarity = similarities[0][best_match_idx]
                    
                    if best_similarity > 0.3:
                        best_phrase = self.semantic_clip_phrases[best_match_idx]
                        path = self.bt_clips.get(best_phrase)
                        if path and Path(path).exists():
                            status("MATCH", f"Semantic match: \"{best_phrase}\" (score: {best_similarity:.2f})")
                            return path
                except Exception as e:
                    warning(f"Semantic matching failed: {e}")
            
            # 6. Try context-aware phrase selection
            context_phrases = self._get_context_aware_phrases()
            if context_phrases:
                for phrase in context_phrases:
                    if normalized in phrase or phrase in normalized:
                        path = self.bt_clips.get(phrase)
                        if path and Path(path).exists():
                            status("MATCH", f"Context-aware: \"{phrase}\"")
                            return path
            
            # 7. Try emotional tone matching
            emotion_phrases = self._get_emotion_matching_phrases(response_text)
            if emotion_phrases:
                for phrase in emotion_phrases:
                    if normalized in phrase or phrase in normalized:
                        path = self.bt_clips.get(phrase)
                        if path and Path(path).exists():
                            status("MATCH", f"Emotion match: \"{phrase}\"")
                            return path
            
            # 8. Try dialogue tree navigation
            dialogue_clip = self._get_dialogue_response(response_text, self.dialogue_state)
            if dialogue_clip and Path(dialogue_clip).exists():
                return dialogue_clip
            
            # 9. Partial matches for common patterns
            common_patterns = {
                "you're welcome": ["thank you", "thanks", "thx"],
                "copy that": ["acknowledged", "understood", "roger"],
                "stand by": ["standby", "waiting", "processing"],
                "retrieving": ["fetching", "accessing", "pulling"],
                "pilot": ["user", "human", "person"]
            }
            
            for standby_key, patterns in common_patterns.items():
                for pattern in patterns:
                    if pattern in normalized:
                        for key, path in self.bt_clips.items():
                            if standby_key in key and Path(path).exists():
                                return path
                        for key, path in self.standby_clips.items():
                            if standby_key in key and Path(path).exists():
                                return path
                                
            return None

        # 2. Handle compound queries - detect all matching query types
        response_parts = []
        handled_types = set()
        skip_normal_tts = False
        followup_tts_text = None
        lower_text = text.lower()

        # Special handling for gratitude expressions
        # Check if gratitude is the ONLY intent (no other actionable commands)
        gratitude_only = self._is_expression_of_gratitude(text)
        if gratitude_only:
            # Check if the same utterance also contains other actionable commands
            has_other_commands = (
                self._is_vpn_toggle_command(text) or
                self._is_todo_command(text) or
                self._is_note_command(text) or
                self._is_weather_query(text) or
                self._is_time_query(text) or
                self._is_location_query(text) or
                self._is_status_query(text) or
                self._is_vpn_status_query(text) or
                self._is_search_query(text) or
                self._is_travel_query(text) or
                self._is_protocol_command(text) or
                self._is_maintenance_command(text)
            )
            if not has_other_commands:
                quote("BT-7274", "You're welcome, Pilot.")
                # Try to play pre-recorded "you're welcome" clip
                key = self._normalize_phrase("you're welcome pilot")
                # First check BT's original clips
                wav_path = self.bt_clips.get(key) or self.standby_clips.get(key)
                if wav_path and Path(wav_path).exists():
                    play_audio(wav_path)
                else:
                    # Try other variations of gratitude responses
                    gratitude_variations = [
                        "you're welcome pilot",
                        "you're welcome",
                        "my pleasure pilot",
                        "glad to assist pilot",
                        "happy to help pilot",
                        "anytime pilot"
                    ]
                    
                    found_clip = False
                    for variation in gratitude_variations:
                        var_key = self._normalize_phrase(variation)
                        var_path = self.standby_clips.get(var_key)
                        if var_path and Path(var_path).exists():
                            play_audio(var_path)
                            found_clip = True
                            break
                            
                    if not found_clip:
                        # Fallback to TTS
                        if self.tts:
                            response_wav = self.tts.speak("You're welcome, Pilot.")
                            if response_wav:
                                play_audio(response_wav)
                self.last_activity = time.time()
                # Update conversation context
                self._update_conversation_context(text, "You're welcome, Pilot.")
                return True
            else:
                # Gratitude mixed with commands - add a gratitude response part
                # and continue processing the rest of the commands below
                response_parts.append("You're welcome, Pilot.")
                handled_types.add("gratitude")

        # Check for location query (but not if part of longer question)
        if self._is_location_query(text):
            status("LOC", "Locating Pilot...")
            try:
                location_result = self.actions.execute("get_location") if self.actions else "Location unavailable"
                if location_result and not location_result.startswith("Location"):
                    status("LOC", location_result)
                    location_text = f"Pilot, {location_result}"
                    response_parts.append(location_text)
                    handled_types.add("location")
                    # Use BT clip + TTS followup for immersive location responses
                    skip_normal_tts = True
                    followup_tts_text = location_text
                else:
                    response_parts.append("Pilot, my navigation systems are currently unable to establish our position.")
                    handled_types.add("location")
            except Exception as e:
                self._report_error("actions", "get_location", e)
                response_parts.append("Pilot, my navigation systems are currently unable to establish our position.")
                handled_types.add("location")

        # Check for time query
        if self._is_time_query(text):
            status("TIME", "Checking chronometer...")
            try:
                time_result = self.actions.execute("tell_time") if self.actions else "Time unavailable"
                date_result = self.actions.execute("tell_date") if self.actions else "Date unavailable"
                if time_result and date_result:
                    status("TIME", time_result)
                    status("DATE", date_result)
                    response_parts.append(f"Pilot, {date_result} {time_result}")
                    handled_types.add("time")
                elif time_result:
                    response_parts.append(f"Pilot, {time_result}")
                    handled_types.add("time")
                else:
                    response_parts.append("Pilot, my chronometer is offline.")
                    handled_types.add("time")
            except Exception as e:
                self._report_error("actions", "tell_time/date", e)
                response_parts.append("Pilot, my chronometer is offline.")
                handled_types.add("time")

        # Check for status query - respond with BT-7274 original voice clips + TTS system status
        if self._is_status_query(text):
            status("DIAG", "Running systems diagnostic...")
            status_clip = self._get_status_response_clip()
            if status_clip:
                try:
                    play_audio(status_clip)
                    quote("BT-7274", "[Status report via original voice clip]")
                    # Generate TTS system status summary after clip
                    status_summary = self._get_system_status_summary()
                    response_parts.append(status_summary)
                    handled_types.add("status")
                    # Use BT clip + TTS followup for immersive status responses
                    skip_normal_tts = True
                    followup_tts_text = status_summary
                except Exception as e:
                    self._report_error("tts", "play_status_clip", e, {"status_clip": status_clip})
                    response_parts.append("Pilot, all systems are operational and ready for deployment.")
                    handled_types.add("status")
            else:
                response_parts.append("Pilot, all systems are operational and ready for deployment.")
                handled_types.add("status")

        # Check for VPN status query
        if self._is_vpn_status_query(text):
            status("VPN", "Checking cloak status...")
            if self.vpn:
                vpn_status = self.vpn.get_status()
                state = vpn_status.get("state", "unknown")
                server = vpn_status.get("server")
                wifi = vpn_status.get("wifi")
                auto_cloak = vpn_status.get("auto_cloak", False)
                if state == "connected":
                    server_str = f" via {server}" if server else ""
                    response_parts.append(f"Cloak is engaged{server_str}, Pilot. Network traffic is obfuscated.")
                else:
                    response_parts.append("Cloak is offline. We are exposed, Pilot.")
                if auto_cloak:
                    response_parts.append("Auto-cloak is enabled.")
                if wifi:
                    response_parts.append(f"Current network: {wifi}.")
            else:
                response_parts.append("VPN monitor is not initialized, Pilot.")
            handled_types.add("vpn")

        # Check for detailed cloak status command
        if any(phrase in lower_text for phrase in ["cloak status", "vpn status", "cloak details", "vpn details"]):
            status("VPN", "Retrieving cloak diagnostics...")
            if self.vpn:
                detailed_status = self.vpn.show_status()
                response_parts.append(detailed_status)
            else:
                response_parts.append("VPN monitor is not initialized, Pilot.")
            handled_types.add("vpn")

        # Check for weather query
        if self._is_weather_query(text):
            status("WEATHER", "Fetching local data...")
            try:
                # Check if user specified a location in the query
                query_location = self._extract_location_from_query(text)
                is_forecast = self._is_forecast_query(text)

                if is_forecast:
                    # Use forecast action
                    if query_location:
                        status("LOC", f"Location from query: {query_location}")
                        weather_result = self.actions.execute("get_weather_forecast", location=query_location) if self.actions else "Weather unavailable"
                    else:
                        weather_result = self.actions.execute("get_weather_forecast") if self.actions else "Weather unavailable"
                else:
                    # Use current weather action
                    if query_location:
                        status("LOC", f"Location from query: {query_location}")
                        weather_result = self.actions.execute("get_weather_for_location", location=query_location) if self.actions else "Weather unavailable"
                    else:
                        weather_result = self.actions.execute("get_weather") if self.actions else "Weather unavailable"

                if weather_result and not weather_result.startswith("Weather data unavailable") and not weather_result.startswith("Forecast data unavailable"):
                    status("WEATHER", weather_result)
                    # Check for raw data request
                    if "raw" in text.lower() or "full" in text.lower():
                        response_parts.append(weather_result)
                    else:
                        log_llm("Summarizing for Pilot...")
                        summary_prompt = (
                            f"Weather data: {weather_result}\n\n"
                            f"Respond in character as BT-7274 with a detailed, complete explanation. "
                            f"Use 3-7 sentences. Be thorough and helpful. "
                            f"NEVER repeat the user's question. Just answer directly. "
                            f"Only the response text. No quotes, no markdown, no extra text."
                        )
                        try:
                            weather_response = self.llm.chat(summary_prompt) if self.llm else f"Failed to summarize weather: {weather_result}"
                            response_parts.append(weather_response)
                            # Use BT clip + TTS followup for immersive weather responses
                            skip_normal_tts = True
                            followup_tts_text = weather_response
                        except Exception as e:
                            self._report_error("llm", "chat_weather_summary", e)
                            response_parts.append(f"Pilot, {weather_result}")
                    handled_types.add("weather")
                else:
                    response_parts.append("Pilot, atmospheric sensors are offline.")
                    handled_types.add("weather")
            except Exception as e:
                self._report_error("actions", "get_weather", e)
                response_parts.append("Pilot, atmospheric sensors are offline.")
                handled_types.add("weather")

        # Check for search intent - always let LLM handle these with search results
        if self._is_search_query(text) and "search" not in handled_types:
            status("SEARCH", "Looking up...")
            try:
                # Enrich query with location context
                enriched_query = self.location.enrich_query(text) if self.location else text
                if enriched_query != text:
                    status("LOC", f"Localized query: {enriched_query}")
                search_result = self.actions.execute("search_web", query=enriched_query) if self.actions else "Search unavailable"
                if search_result and not search_result.startswith("Action") and not search_result.startswith("Search failed"):
                    status("SEARCH", f"Results: {search_result[:100]}...")
                    log_llm("Summarizing for Pilot...")
                    # Check if this is a news query
                    is_news_query = any(word in text.lower() for word in ["news", "latest", "breaking"])
                    if is_news_query:
                        summary_prompt = (
                            f"Search results: {search_result}\n\n"
                            f"Respond in character as BT-7274. Provide a concise summary of the most relevant news. "
                            f"Focus on the key facts from the search results. "
                            f"Use 2-4 sentences. Be direct and informative. "
                            f"NEVER repeat the user's question. Just answer directly. "
                            f"Only the response text. No quotes, no markdown, no extra text."
                        )
                    else:
                        summary_prompt = (
                            f"Search results: {search_result}\n\n"
                            f"Respond in character as BT-7274 with a detailed, complete explanation. "
                            f"Use 3-7 sentences. Be thorough and helpful. "
                            f"NEVER repeat the user's question. Just answer directly. "
                            f"Only the response text. No quotes, no markdown, no extra text."
                        )
                    try:
                        search_response = self.llm.chat(summary_prompt) if self.llm else f"Failed to summarize search: {search_result}"
                        response_parts.append(search_response)
                    except Exception as e:
                        self._report_error("llm", "chat_search_summary", e)
                        response_parts.append(f"Pilot, {search_result}")
                    handled_types.add("search")
                else:
                    response_parts.append("Pilot, my sensors cannot reach the data network at this time.")
                    handled_types.add("search")
            except Exception as e:
                self._report_error("actions", "search_web", e)
                response_parts.append("Pilot, my sensors cannot reach the data network at this time.")
                handled_types.add("search")

        # Check for TTS cache clearing request
        if "clear tts cache" in text.lower() or "clear cache" in text.lower():
            cache_hit("Clearing TTS cache...")
            self.clear_tts_cache()
            response_parts.append("TTS cache cleared, Pilot.")
            handled_types.add("maintenance")

        # Check for environmental warnings toggle
        lower_text = text.lower()
        if any(phrase in lower_text for phrase in ["turn on weather warnings", "enable weather warnings", "turn on environmental warnings", "enable environmental warnings"]):
            if self.weather:
                self.weather.enabled = True
                self.weather.start()
                response_parts.append("Environmental warnings enabled, Pilot.")
            else:
                response_parts.append("Environmental monitor is not initialized, Pilot.")
            handled_types.add("maintenance")
        elif any(phrase in lower_text for phrase in ["turn off weather warnings", "disable weather warnings", "turn off environmental warnings", "disable environmental warnings"]):
            if self.weather:
                self.weather.enabled = False
                self.weather.stop()
                response_parts.append("Environmental warnings disabled, Pilot.")
            else:
                response_parts.append("Environmental monitor is not initialized, Pilot.")
            handled_types.add("maintenance")

        # Check for VPN / auto-cloak toggle
        if any(phrase in lower_text for phrase in ["enable auto cloak", "turn on auto cloak", "enable auto-cloak", "turn on auto-cloak", "enable vpn auto connect", "turn on vpn auto connect"]):
            if self.vpn:
                self.vpn.auto_cloak = True
                response_parts.append("Auto-cloak enabled, Pilot. I will warn you on public networks.")
            else:
                response_parts.append("VPN monitor is not initialized, Pilot.")
            handled_types.add("maintenance")
        elif any(phrase in lower_text for phrase in ["disable auto cloak", "turn off auto cloak", "disable auto-cloak", "turn off auto-cloak", "disable vpn auto connect", "turn off vpn auto connect"]):
            if self.vpn:
                self.vpn.auto_cloak = False
                response_parts.append("Auto-cloak disabled, Pilot.")
            else:
                response_parts.append("VPN monitor is not initialized, Pilot.")
            handled_types.add("maintenance")
        elif any(phrase in lower_text for phrase in ["enable vpn monitor", "turn on vpn monitor", "enable cloak monitor", "turn on cloak monitor"]):
            if self.vpn:
                self.vpn.enabled = True
                self.vpn.start()
                response_parts.append("VPN cloak monitor enabled, Pilot.")
            else:
                response_parts.append("VPN monitor is not initialized, Pilot.")
            handled_types.add("maintenance")
        elif any(phrase in lower_text for phrase in ["disable vpn monitor", "turn off vpn monitor", "disable cloak monitor", "turn off cloak monitor"]):
            if self.vpn:
                self.vpn.enabled = False
                self.vpn.stop()
                response_parts.append("VPN cloak monitor disabled, Pilot.")
            else:
                response_parts.append("VPN monitor is not initialized, Pilot.")
            handled_types.add("maintenance")

        # Check for direct VPN/cloak on/off commands
        if self._is_vpn_toggle_command(text) and "maintenance" not in handled_types:
            lower = text.lower()
            # Determine if turning on or off
            on_phrases = [
                "turn on the vpn", "turn on vpn", "turn on cloak", "turn on the cloak",
                "enable vpn", "enable cloak", "enable the vpn", "enable the cloak",
                "put on cloak", "put on the cloak", "put on vpn", "put on the vpn",
                "activate vpn", "activate cloak", "activate the vpn", "activate the cloak",
                "start vpn", "start cloak", "start the vpn", "start the cloak",
                "engage cloak", "engage vpn", "engage the cloak", "engage the vpn",
                "cloak on", "vpn on"
            ]
            off_phrases = [
                "turn off the vpn", "turn off vpn", "turn off cloak", "turn off the cloak",
                "disable vpn", "disable cloak", "disable the vpn", "disable the cloak",
                "take off cloak", "take off the cloak", "take off vpn", "take off the vpn",
                "deactivate vpn", "deactivate cloak", "deactivate the vpn", "deactivate the cloak",
                "stop vpn", "stop cloak", "stop the vpn", "stop the cloak",
                "disengage cloak", "disengage vpn", "disengage the cloak", "disengage the vpn",
                "cloak off", "vpn off"
            ]
            is_turning_on = any(phrase in lower for phrase in on_phrases)
            is_turning_off = any(phrase in lower for phrase in off_phrases)
            
            if is_turning_on:
                status("VPN", "Engaging cloak...")
                try:
                    # Try to connect VPN using the VPN monitor
                    if self.vpn:
                        result = self.vpn.connect_and_wait(timeout=15)
                        if result:
                            response_parts.append("Cloak engaged, Pilot. Network traffic is now obfuscated.")
                        else:
                            response_parts.append("Cloak connection timed out, Pilot. Check System Settings > VPN for status.")
                    else:
                        response_parts.append("VPN monitor is not initialized, Pilot.")
                except Exception as e:
                    self._report_error("vpn", "connect", e)
                    response_parts.append("Cloak engagement failed, Pilot.")
                handled_types.add("vpn")
            elif is_turning_off:
                status("VPN", "Disengaging cloak...")
                try:
                    if self.vpn:
                        result = self.vpn.disconnect()
                        if result:
                            response_parts.append("Cloak disengaged, Pilot. We are exposed.")
                        else:
                            response_parts.append("Unable to disengage cloak at this time, Pilot.")
                    else:
                        response_parts.append("VPN monitor is not initialized, Pilot.")
                except Exception as e:
                    self._report_error("vpn", "disconnect", e)
                    response_parts.append("Cloak disengagement failed, Pilot.")
                handled_types.add("vpn")

        # Check for Protocol Mode commands
        lower_text = text.lower()
        if "protocol brief" in lower_text:
            status("PROTOCOL", "Generating protocol brief...")
            try:
                if self.protocol_brief:
                    brief = self.protocol_brief.get_brief()
                    response_parts.append(brief)
                    logger.info(f"[PROTOCOL] Protocol brief generated for pilot")
                else:
                    response_parts.append("Protocol Brief system is offline, Pilot.")
                    logger.warning("[PROTOCOL] Protocol brief requested but system is offline")
            except Exception as e:
                self._report_error("protocol_brief", "get_brief", e)
                response_parts.append("Unable to generate protocol brief at this time.")
            handled_types.add("protocol")

        # Check for Protocol Mode toggle
        if any(phrase in lower_text for phrase in ["enable protocol mode", "turn on protocol mode", "activate protocol mode"]):
            self.protocol_mode_enabled = True
            response_parts.append("Protocol Mode enabled, Pilot.")
            logger.info("[PROTOCOL] Protocol Mode enabled by pilot command")
            handled_types.add("protocol")
        elif any(phrase in lower_text for phrase in ["disable protocol mode", "turn off protocol mode", "deactivate protocol mode"]):
            self.protocol_mode_enabled = False
            response_parts.append("Protocol Mode disabled, Pilot.")
            logger.info("[PROTOCOL] Protocol Mode disabled by pilot command")
            handled_types.add("protocol")

        # Check for mission briefing commands
        if any(phrase in lower_text for phrase in ["set mission", "new mission", "update mission", "mission is"]):
            status("PROTOCOL", "Updating mission briefing...")
            try:
                if self.protocol_brief:
                    # Extract mission text after the command phrase
                    mission_text = text
                    for phrase in ["set mission", "new mission", "update mission", "mission is"]:
                        if phrase in lower_text:
                            mission_text = text[lower_text.find(phrase) + len(phrase):].strip()
                            mission_text = mission_text.lstrip(",.:; ")
                            break
                    if mission_text:
                        result = self.protocol_brief.set_mission(mission_text)
                        response_parts.append(result)
                        logger.info(f"[PROTOCOL] Mission updated: {mission_text}")
                    else:
                        response_parts.append("Please specify mission details, Pilot.")
                else:
                    response_parts.append("Protocol Brief system is offline, Pilot.")
            except Exception as e:
                self._report_error("protocol_brief", "set_mission", e)
                response_parts.append("Failed to update mission briefing.")
            handled_types.add("protocol")

        if any(phrase in lower_text for phrase in ["what is the mission", "current mission", "mission status", "mission brief"]):
            status("PROTOCOL", "Retrieving mission briefing...")
            try:
                if self.protocol_brief:
                    mission = self.protocol_brief.get_mission()
                    if mission:
                        response_parts.append(f"Current mission: {mission}")
                    else:
                        response_parts.append("No active mission briefing, Pilot.")
                    logger.info("[PROTOCOL] Mission briefing retrieved")
                else:
                    response_parts.append("Protocol Brief system is offline, Pilot.")
            except Exception as e:
                self._report_error("protocol_brief", "get_mission", e)
                response_parts.append("Failed to retrieve mission briefing.")
            handled_types.add("protocol")

        if any(phrase in lower_text for phrase in ["clear mission", "delete mission", "end mission"]):
            status("PROTOCOL", "Clearing mission briefing...")
            try:
                if self.protocol_brief:
                    result = self.protocol_brief.clear_mission()
                    response_parts.append(result)
                    logger.info("[PROTOCOL] Mission briefing cleared")
                else:
                    response_parts.append("Protocol Brief system is offline, Pilot.")
            except Exception as e:
                self._report_error("protocol_brief", "clear_mission", e)
                response_parts.append("Failed to clear mission briefing.")
            handled_types.add("protocol")

        # Check for to-do commands (using improved detection)
        if self._is_todo_command(text):
            status("PROTOCOL", "Adding to-do...")
            try:
                # Extract task text after the command phrase
                task_text = text
                # Expanded list of command phrases to strip
                todo_phrases = [
                    "add to my to do list", "add to my todo list",
                    "add to the to do list", "add to the todo list",
                    "add to do list", "add todo list",
                    "put on my to do list", "put on my todo list",
                    "put on the to do list", "put on the todo list",
                    "put on to do list", "put on todo list",
                    "add todo", "add task", "new task", "new todo"
                ]
                for phrase in todo_phrases:
                    if phrase in lower_text:
                        task_text = text[lower_text.find(phrase) + len(phrase):].strip()
                        # Strip leading punctuation
                        task_text = task_text.lstrip(",.:; ")
                        break
                if task_text:
                    if self.protocol_brief:
                        result = self.protocol_brief.add_todo(task_text)
                        response_parts.append(result)
                        logger.info(f"[PROTOCOL] To-do added: {task_text}")
                    else:
                        response_parts.append("Protocol Brief system is offline, Pilot.")
                else:
                    response_parts.append("Please specify a task to add, Pilot.")
            except Exception as e:
                self._report_error("protocol_brief", "add_todo", e)
                response_parts.append("Failed to add to-do item.")
            handled_types.add("protocol")

        if any(phrase in lower_text for phrase in ["list tasks", "list todos", "show tasks", "show todos", "what are my tasks"]):
            status("PROTOCOL", "Listing to-dos...")
            try:
                if self.protocol_brief:
                    result = self.protocol_brief.list_todo()
                    response_parts.append(result)
                    logger.info("[PROTOCOL] To-do list retrieved")
                else:
                    response_parts.append("Protocol Brief system is offline, Pilot.")
            except Exception as e:
                self._report_error("protocol_brief", "list_todo", e)
                response_parts.append("Failed to list to-do items.")
            handled_types.add("protocol")

        if any(phrase in lower_text for phrase in ["clear completed", "clear done tasks"]):
            status("PROTOCOL", "Clearing completed tasks...")
            try:
                if self.protocol_brief:
                    result = self.protocol_brief.clear_todo()
                    response_parts.append(result)
                    logger.info("[PROTOCOL] Completed to-dos cleared")
                else:
                    response_parts.append("Protocol Brief system is offline, Pilot.")
            except Exception as e:
                self._report_error("protocol_brief", "clear_todo", e)
                response_parts.append("Failed to clear completed tasks.")
            handled_types.add("protocol")

        # Check for note commands
        if any(phrase in lower_text for phrase in ["add note", "make note", "write note", "take note"]):
            status("PROTOCOL", "Adding note...")
            try:
                note_text = text
                for phrase in ["add note", "make note", "write note", "take note"]:
                    if phrase in lower_text:
                        note_text = text[lower_text.find(phrase) + len(phrase):].strip()
                        break
                if note_text:
                    if self.protocol_brief:
                        result = self.protocol_brief.add_note(note_text)
                        response_parts.append(result)
                        logger.info(f"[PROTOCOL] Note added: {note_text}")
                    else:
                        response_parts.append("Protocol Brief system is offline, Pilot.")
                else:
                    response_parts.append("Please specify note content, Pilot.")
            except Exception as e:
                self._report_error("protocol_brief", "add_note", e)
                response_parts.append("Failed to add note.")
            handled_types.add("protocol")

        if any(phrase in lower_text for phrase in ["list notes", "show notes", "read notes", "view notes"]):
            status("PROTOCOL", "Listing notes...")
            try:
                if self.protocol_brief:
                    result = self.protocol_brief.list_notes()
                    response_parts.append(result)
                    logger.info("[PROTOCOL] Notes list retrieved")
                else:
                    response_parts.append("Protocol Brief system is offline, Pilot.")
            except Exception as e:
                self._report_error("protocol_brief", "list_notes", e)
                response_parts.append("Failed to list notes.")
            handled_types.add("protocol")

        # Check for log commands (read logs, make log, delete log)
        if self._is_log_command(text) and "log" not in handled_types:
            import re
            lower = text.lower()
            # Determine log type
            is_bt_log = any(phrase in lower for phrase in ["bt log", "system log", "bt-7274 log"])
            is_delete = bool(re.search(r"\b(delete|clear|remove)\b.*\b(logs?|my\s+logs?)\b", lower))
            is_make_log = bool(re.search(r"\b(make|create|write|add)\b.*\b(logs?|entry|note)\b", lower)) or bool(re.search(r"\blog\b.*\b(this|that|it)\b", lower))
            
            if is_delete:
                status("LOG", "Clearing logs...")
                try:
                    from bt7274_workstation.pilot_logger import PilotLogger
                    pilot_logger = PilotLogger()
                    if is_bt_log:
                        result = pilot_logger.delete_bt_logs()
                    else:
                        result = pilot_logger.delete_pilot_logs()
                    response_parts.append(result)
                    # Try to play a pre-recorded log voice line
                    log_clip = self._get_log_clip("delete")
                    if log_clip:
                        play_audio(log_clip)
                except Exception as e:
                    self._report_error("pilot_logger", "delete_logs", e)
                    response_parts.append("Failed to clear logs, Pilot.")
                handled_types.add("log")
            elif is_make_log:
                status("LOG", "Creating log entry...")
                try:
                    # Extract log text after the command phrase using regex
                    import re
                    log_text = text
                    # Match patterns like "make a personal log", "create log", "log this"
                    make_patterns = [
                        r"(?:make|create|write|add)\s+(?:a\s+)?(?:personal\s+)?(?:bt\s+)?(?:system\s+)?(?:log|entry|note)[,:\s]*(.+)",
                        r"(?:log|save)\s+(?:this|that|it)[,:\s]*(.+)",
                    ]
                    for pattern in make_patterns:
                        match = re.search(pattern, lower)
                        if match:
                            log_text = match.group(1).strip()
                            break
                    else:
                        # Fallback: strip command words from beginning
                        log_text = re.sub(r"^(?:bt[,\s]+)?(?:make|create|write|add|log|save)\s+(?:a\s+)?(?:personal\s+)?(?:bt\s+)?(?:system\s+)?(?:log|entry|note)?[,:\s]*", "", text, flags=re.IGNORECASE).strip()
                    
                    if log_text:
                        from bt7274_workstation.pilot_logger import PilotLogger
                        pilot_logger = PilotLogger()
                        if is_bt_log:
                            result = pilot_logger.log_bt(log_text)
                        else:
                            result = pilot_logger.log_pilot(log_text)
                        response_parts.append(result)
                        # Try to play a pre-recorded log voice line
                        log_clip = self._get_log_clip("create")
                        if log_clip:
                            play_audio(log_clip)
                    else:
                        response_parts.append("Please specify log content, Pilot.")
                except Exception as e:
                    self._report_error("pilot_logger", "make_log", e)
                    response_parts.append("Failed to create log entry, Pilot.")
                handled_types.add("log")
            else:
                # Read logs
                status("LOG", "Retrieving logs...")
                try:
                    from bt7274_workstation.pilot_logger import PilotLogger
                    pilot_logger = PilotLogger()
                    if is_bt_log:
                        result = pilot_logger.read_bt_logs(lines=10)
                    else:
                        result = pilot_logger.read_pilot_logs(lines=10)
                    response_parts.append(result)
                    # Try to play a pre-recorded log voice line
                    log_clip = self._get_log_clip("read")
                    if log_clip:
                        play_audio(log_clip)
                    # Read the log content via TTS for accessibility
                    if result and not result.startswith("No"):
                        # Summarize for TTS - just read the most recent entries
                        lines = result.strip().split("\n")
                        if len(lines) > 2:
                            tts_summary = "Here are your recent log entries, Pilot. " + " ".join(lines[-3:])
                        else:
                            tts_summary = result
                        skip_normal_tts = True
                        followup_tts_text = tts_summary
                except Exception as e:
                    self._report_error("pilot_logger", "read_logs", e)
                    response_parts.append("Failed to retrieve logs, Pilot.")
                handled_types.add("log")

        # Check for travel queries - always let LLM handle these with location context
        # But don't process travel context for event information queries (dates, prices, etc.)
        is_information_query = self._is_event_information_query(text)
        is_travel_related = (self._is_travel_query(text) or self._mentions_destination(text) or 
                           self._is_requesting_travel_options(text) or self._is_travel_query_complex(text))
        
        if is_travel_related and "travel" not in handled_types and not is_information_query:
            # For travel queries, silently get user's location and inject it into the LLM prompt
            status("LOC", "Checking your location for travel planning...")
            location_result = self.actions.execute("get_location_structured") if self.actions else "Location unavailable"
            if location_result and not location_result.startswith("Location"):
                try:
                    location_data = json.loads(location_result)
                    location_context = f"IMPORTANT PILOT LOCATION DATA - USE THIS EXACT LOCATION, DO NOT ASSUME ANY OTHER LOCATION: {location_data.get('formatted', 'Unknown')}. Coordinates: {location_data.get('coordinates', {}).get('latitude', 'N/A')}, {location_data.get('coordinates', {}).get('longitude', 'N/A')}. City: {location_data.get('city', 'Unknown')}."
                    # Add location context to the query - let LLM handle the full question
                    enriched_text = f"{text} {location_context} DO NOT MENTION GAME WORLD LOCATIONS OR FICTIONAL PLACES. USE THE PROVIDED REAL-WORLD GEOGRAPHIC INFORMATION."
                    log_llm("Thinking with location context...")
                    travel_response = self.llm.chat(enriched_text) if self.llm else "Travel information unavailable"
                    response_parts.append(travel_response)
                    handled_types.add("travel")
                except json.JSONDecodeError:
                    # Fallback to simple location if JSON parsing fails
                    simple_location = self.actions.execute("get_location") if self.actions else "Location unavailable"
                    if simple_location and not simple_location.startswith("Location"):
                        enriched_text = f"{text} IMPORTANT PILOT LOCATION DATA - USE THIS EXACT LOCATION, DO NOT ASSUME ANY OTHER LOCATION: {simple_location} DO NOT MENTION GAME WORLD LOCATIONS OR FICTIONAL PLACES. USE THE PROVIDED REAL-WORLD GEOGRAPHIC INFORMATION."
                        log_llm("Thinking with location context...")
                        travel_response = self.llm.chat(enriched_text) if self.llm else "Travel information unavailable"
                        response_parts.append(travel_response)
                        handled_types.add("travel")
                    else:
                        log_llm("Thinking...")
                        normal_response = self.llm.chat(text) if self.llm else "Response unavailable"
                        response_parts.append(normal_response)
                        handled_types.add("travel")
            else:
                log_llm("Thinking...")
                normal_response = self.llm.chat(text) if self.llm else "Response unavailable"
                response_parts.append(normal_response)
                handled_types.add("travel")
        elif is_information_query and "travel" not in handled_types and is_travel_related:
            # For event information queries, process normally without location context
            log_llm("Thinking...")
            normal_response = self.llm.chat(text) if self.llm else "Response unavailable"
            response_parts.append(normal_response)
            handled_types.add("travel")

        # Combine responses or fall back to normal processing
        llm_response_time = None
        if response_parts:
            # Combine all collected responses
            response = " ".join(response_parts)
        elif not handled_types:
            # No specific handlers matched, use normal LLM processing
            log_llm("Thinking...")
            llm_start = time.time()
            try:
                response = self.llm.chat(text) if self.llm else "Response unavailable"
            except Exception as e:
                self._report_error("llm", "chat", e, {"pilot_message": text})
                response = "Pilot, my neural network is experiencing interference. Please try again."
            llm_response_time = time.time() - llm_start
        else:
            # This shouldn't happen, but just in case
            response = "Processing complete, Pilot."

        # Try to parse and execute any actions embedded in the LLM response
        # This handles cases where the LLM outputs action JSON instead of natural language
        if self.actions and response and not response.startswith("Pilot,"):
            try:
                action_result = self.actions.parse_and_execute(response)
                if action_result and not action_result.startswith("Action") and not action_result.startswith("Unknown"):
                    # Action was executed successfully, use the result as the response
                    response = action_result
            except Exception:
                pass

        # Strip markdown, JSON, and instruction blocks before TTS
        import re
        clean_response = response
        # Remove markdown headers, code blocks, horizontal rules
        clean_response = re.sub(r'#{1,6}\s+.*', '', clean_response)
        clean_response = re.sub(r'```.*?```', '', clean_response, flags=re.DOTALL)
        clean_response = re.sub(r'---+', '', clean_response)
        clean_response = re.sub(r'\*\*.*?\*\*', '', clean_response)
        clean_response = re.sub(r'\{[^{}]*"action"[^{}]*\}', '', clean_response)
        clean_response = clean_response.strip()
        # Collapse multiple blank lines
        clean_response = '\n'.join(line for line in clean_response.splitlines() if line.strip())
        
        # Strip meta-text and action narration that the LLM sometimes outputs
        # Remove lines that describe actions being taken
        meta_patterns = [
            r'(?i)^\s*bt[-\s]?7274?\s+(?:uses?|initiates?|performs?|executes?|triggers?|activates?|engages?|starts?|clears?|clears?\s+the)\s+.*$',
            r'(?i)^\s*bt[-\s]?7274?\s+(?:is\s+)?(?:now\s+)?(?:using|initiating|performing|executing|triggering|activating|engaging|starting|clearing)\s+.*$',
            r'(?i)^\s*(?:simultaneously|meanwhile|at\s+the\s+same\s+time)\s*,?\s*bt[-\s]?7274?\s+.*$',
            r'(?i)^\s*bt[-\s]?7274?\s+(?:also|additionally|furthermore|moreover)\s+.*$',
            r'(?i)^\s*(?:action|system|protocol)\s*:.*$',
            r'(?i)^\s*\[.*?\]\s*bt[-\s]?7274?\s+.*$',
            r'(?i)^\s*bt[-\s]?7274?\s+\[.*?\]\s+.*$',
            r'(?i)^\s*based\s+on\s+the\s+information\s+given.*$',
            r'(?i)^\s*however,\s+without\s+a\s+specified.*$',
            r'(?i)^\s*your\s+transport\s+method\s+seems\s+like.*$',
            r'(?i)^\s*since\s+these\s+are\s+typical\s+modes\s+of\s+travel.*$',
            r'(?i)^\s*bt[-\s]?7274?\s+.*\s+(?:action|cache|tts|weather|forecast|location|data)\s+.*$',
            r'(?i)^\s*bt[-\s]?7274?\s+.*\s+`[^`]+`\s+.*$',
        ]
        lines = clean_response.splitlines()
        filtered_lines = []
        for line in lines:
            if not any(re.match(pattern, line) for pattern in meta_patterns):
                filtered_lines.append(line)
        clean_response = '\n'.join(filtered_lines)
        
        # Enforce conciseness: limit to first 3 sentences max
        sentences = re.split(r'(?<=[.!?])\s+', clean_response)
        if len(sentences) > 3:
            clean_response = ' '.join(sentences[:3]).strip()
        
        # Also hard-cap at 300 characters as a safety net
        if len(clean_response) > 300:
            # Find the last sentence boundary before 300 chars
            truncated = clean_response[:300]
            last_period = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
            if last_period > 0:
                clean_response = truncated[:last_period + 1].strip()
            else:
                clean_response = truncated.strip() + "..."
        
        # Post-process to correct location inaccuracies
        if "New London" in clean_response:
            # Try to get actual location and replace New London references
            try:
                from bt7274_workstation.location import LocationProvider
                loc = LocationProvider()
                if loc.update():
                    actual_location = loc.location_str
                    clean_response = clean_response.replace("New London", actual_location)
            except:
                pass
        
        if not clean_response:
            clean_response = "Processing complete, Pilot."

        quote("BT-7274", clean_response)

        # 4. Text-to-Speech
        log_tts("Synthesizing voice...")
        output_wav = None  # Initialize to prevent unbound variable errors

        # If a handler requested clip+TTS followup (e.g. location), use that instead
        followup_result = None
        if skip_normal_tts and followup_tts_text:
            followup_result = self._play_bt_clip_with_tts_followup(followup_tts_text, followup_tts_text)
            tts_success = followup_result["tts_played"] or followup_result["clip_played"]
            standby_wav = None
            clip_source = "bt_clip" if followup_result["clip_played"] else None
            clip_phrase = followup_result["clip_phrase"]
        else:
            # Try to use a standby clip for common responses to reduce latency
            standby_wav = try_standby_for_response(clean_response)
            tts_success = False
            clip_source = None
            clip_phrase = None
            
            if standby_wav and Path(standby_wav).exists():
                # Determine if it's a BT clip or standby clip
                if standby_wav in self.bt_clips.values():
                    clip_source = "bt_clip"
                    # Find the phrase for this BT clip
                    for phrase, path in self.bt_clips.items():
                        if path == standby_wav:
                            clip_phrase = phrase
                            break
                    if clip_phrase:
                        clip_play(clip_phrase, source="BT-7274 original")
                else:
                    clip_source = "standby_clip"
                    # Find the phrase for this standby clip
                    for phrase, path in self.standby_clips.items():
                        if path == standby_wav:
                            clip_phrase = phrase
                            break
                    if clip_phrase:
                        clip_play(clip_phrase, source="standby")
                
                try:
                    play_audio(standby_wav)
                    tts_success = True
                except Exception as e:
                    self._report_error("tts", "play_standby", e, {"standby_wav": standby_wav, "clip_source": clip_source, "clip_phrase": clip_phrase})
            else:
                # Use appropriate TTS method based on performance mode
                try:
                    if self.performance_mode == "performance" and self.tts:
                        # Performance mode: Use streaming TTS for sentence-level playback
                        log_tts("Streaming TTS (sentence-level)...")
                        if self.tts and hasattr(self.tts, 'speak_streaming') and callable(getattr(self.tts, 'speak_streaming', None)):
                            try:
                                self.tts.speak_streaming(clean_response)  # type: ignore[attr-defined]
                                tts_success = True
                            except Exception as e:
                                self._report_error("tts", "speak_streaming", e, {"text": clean_response})
                                tts_success = False
                        elif self.tts and hasattr(self.tts, 'speak') and callable(getattr(self.tts, 'speak', None)):
                            # Fallback to standard TTS if streaming not available
                            try:
                                output_wav = self.tts.speak(clean_response)
                                if output_wav:
                                    try:
                                        play_audio(output_wav)
                                        tts_success = True
                                    except Exception as play_error:
                                        self._report_error("tts", "play_audio", play_error, {"output_wav": output_wav})
                                        tts_success = False
                            except Exception as e:
                                self._report_error("tts", "speak", e, {"text": clean_response})
                                tts_success = False
                        else:
                            # Fallback to standard TTS if streaming not available
                            output_wav = self.tts.speak(clean_response) if self.tts else None
                            if output_wav:
                                try:
                                    play_audio(output_wav)
                                    tts_success = True
                                except Exception as play_error:
                                    self._report_error("tts", "play_audio", play_error, {"output_wav": output_wav})
                    elif self.tts:
                        # Standard mode: Full response synthesis then playback
                        output_wav = self.tts.speak(clean_response) if self.tts else None
                        if output_wav:
                            try:
                                play_audio(output_wav)
                                tts_success = True
                            except Exception as e:
                                self._report_error("tts", "play_audio", e, {"output_wav": output_wav})
                except Exception as e:
                    self._report_error("tts", "speak", e, {"text": clean_response})

        # Update conversation context with the current interaction
        self._update_conversation_context(text, clean_response)

        # Log the interaction (after TTS so metrics are accurate)
        # For performance mode, use last_metrics from streaming session
        if self.performance_mode == "performance" and self.tts and hasattr(self.tts, '_last_metrics'):
            tts_metrics = self.tts._last_metrics.copy() if self.tts._last_metrics else {}
        else:
            tts_metrics = getattr(self.tts, 'get_metrics', lambda: {})() if self.tts else {}
        
        # Determine cache hit type
        cache_hit_type = None
        if standby_wav and Path(standby_wav).exists():
            cache_hit_type = "standby_clip"
        elif tts_metrics and tts_metrics.get("cached"):
            cache_hit_type = "tts_cache"
        
        # Get audio file path
        audio_file_path = None
        if not (standby_wav and Path(standby_wav).exists()):
            if self.performance_mode == "performance":
                audio_file_path = "streaming"
            else:
                audio_file_path = output_wav if output_wav else None
        
        # Get location context
        location_context = None
        if self.location and self.location.location_str:
            location_context = self.location.location_str
        
        # Get weather context (if weather was queried)
        weather_context = None
        weather_result = None  # Initialize to prevent unbound variable error
        if "weather" in handled_types:
            weather_context = weather_result if 'weather_result' in locals() and weather_result else None
        
        # Calculate mission elapsed time
        mission_elapsed_time = time.time() - self.session_start_time
        
        # Calculate conversation duration (time since last interaction)
        conversation_duration = time.time() - self.last_activity
        
        # Increment interaction count and update trust level
        self.interaction_count += 1
        if self.interaction_count > 10:
            self.pilot_trust_level = min(5, self.pilot_trust_level + 1)
        
        # Determine protocol reference based on interaction type
        protocol_reference = "Protocol 1: Link to Pilot"
        if "weather" in handled_types or "location" in handled_types:
            protocol_reference = "Protocol 2: Uphold the Mission"
        elif any(err in str(handled_types) for err in ["error", "fail"]):
            protocol_reference = "Protocol 3: Protect the Pilot"
        
        # Apply cooldown to prevent protocol reference spam
        current_time = time.time()
        if protocol_reference == self._last_protocol_reference and current_time < self._protocol_cooldown_until:
            # Same protocol as last time and still in cooldown - suppress it
            protocol_reference = None
        else:
            # New protocol or cooldown expired - update tracking
            self._last_protocol_reference = protocol_reference
            self._protocol_cooldown_until = current_time + self._protocol_cooldown_seconds
        
        # Collect errors (only those from this interaction)
        errors = self.errors_this_interaction if self.errors_this_interaction else None
        
        # Collect actions executed
        actions_executed = list(handled_types) if handled_types else None
        
        # Get wake word used
        wake_word = None
        if not skip_wake_word:
            wake_words = self.config["pipeline"].get("wake_words", [])
            for ww in wake_words:
                if ww.lower() in text.lower():
                    wake_word = ww
                    break
        
        # Prepare enhanced metadata for logging
        enhanced_metadata = {
            "handled_types": list(handled_types) if 'handled_types' in locals() else [],
            "match_type": getattr(self, '_last_match_type', None),
            "match_score": getattr(self, '_last_match_score', None),
            "personality_weights": self.personality_weights.copy(),
            "dialogue_state": self.dialogue_state,
            "emotion_detected": self.current_context.get("bot_emotion", "neutral"),
            "user_emotion": self.current_context.get("user_emotion", "neutral"),
            "context_topic": self.current_context.get("topic", "general"),
            "conversation_history_length": len(self.conversation_history),
            "semantic_similarity_available": SEMANTIC_SIMILARITY_AVAILABLE,
            "clip_source": clip_source,
            "clip_phrase": clip_phrase,
            "tts_triggered": tts_success,
            "tts_synthesized": followup_result["tts_synthesized"] if followup_result else (tts_metrics.get("cached") is not None or tts_metrics.get("processing_time") is not None),
            "clip_played": followup_result["clip_played"] if followup_result else (clip_source is not None),
            "bt_running": self.running,
            "protocol_mode_enabled": self.protocol_mode_enabled,
        }
        
        self.logger.log_interaction(
            pilot_message=text,
            bt_response=clean_response,
            interaction_type="chat" if self.console_chat_mode else "voice",
            ai_mode=self.ai_mode,
            performance_mode=self.performance_mode or "standard",
            tts_metrics=tts_metrics if tts_metrics else None,
            llm_response_time=llm_response_time if 'llm_response_time' in locals() else None,
            stt_confidence=stt_confidence,
            audio_file_path=audio_file_path,
            cache_hit=cache_hit_type,
            token_usage=None,  # Ollama doesn't expose token usage easily
            wake_word=wake_word,
            follow_up_depth=follow_up_depth,
            session_id=self.session_id,
            conversation_duration=conversation_duration,
            protocol_reference=protocol_reference,
            pilot_trust_level=self.pilot_trust_level,
            mission_elapsed_time=mission_elapsed_time,
            actions_executed=actions_executed,
            errors=errors,
            location_context=location_context,
            weather_context=weather_context,
            metadata=enhanced_metadata,
        )

        self.last_activity = time.time()

        # Clear per-interaction errors for the next turn
        self.errors_this_interaction = []

        # 5. Listen for follow-up if BT asked a question (voice mode only)
        max_depth = self.config["pipeline"].get("follow_up", {}).get("max_depth", 1)
        if not self.console_chat_mode and follow_up_depth < max_depth:
            self._listen_for_follow_up(follow_up_depth)

        return True

    def _listen_for_follow_up(self, follow_up_depth: int):
        """Listen for a follow-up response after BT speaks."""
        timeout = self.config["pipeline"].get("follow_up", {}).get("timeout_seconds", 8)
        stop_phrases = self.config["pipeline"].get("follow_up", {}).get("stop_phrases", ["no", "never mind", "stop", "that's all", "goodbye", "exit", "quit"])

        # Small pause to let speaker echo settle
        time.sleep(0.5)

        listening("Listening for follow-up... (speak now)")
        audio_path = self.recorder.record(max_seconds=timeout) if self.recorder else record_until_silence(self.config["stt"], max_seconds=timeout)

        if not audio_path:
            return

        log_stt("Transcribing follow-up...")
        stt_result = self.stt.transcribe(audio_path) if self.stt else {"text": "", "confidence": 0.0}
        text = stt_result.get("text", "") if isinstance(stt_result, dict) else str(stt_result)

        # Clean up temp file
        try:
            os.remove(audio_path)
        except:
            pass

        if not text or not text.strip():
            error("No speech detected in follow-up.")
            return

        text = text.strip()
        quote("Pilot", text)

        # Check for gratitude expressions FIRST (before stop phrases)
        if self._is_expression_of_gratitude(text):
            quote("BT-7274", "You're welcome, Pilot.")
            # Try to play pre-recorded "you're welcome" clip
            key = self._normalize_phrase("you're welcome pilot")
            wav_path = self.standby_clips.get(key)
            if wav_path and Path(wav_path).exists():
                play_audio(wav_path)
            else:
                # Try other variations of gratitude responses
                gratitude_variations = [
                    "you're welcome pilot",
                    "you're welcome",
                    "my pleasure pilot",
                    "glad to assist pilot",
                    "happy to help pilot",
                    "anytime pilot"
                ]
                
                found_clip = False
                for variation in gratitude_variations:
                    var_key = self._normalize_phrase(variation)
                    var_path = self.standby_clips.get(var_key)
                    if var_path and Path(var_path).exists():
                        play_audio(var_path)
                        found_clip = True
                        break
                        
                if not found_clip:
                    # Fallback to TTS
                    if self.tts:
                        response_wav = self.tts.speak("You're welcome, Pilot.")
                        if response_wav:
                            play_audio(response_wav)
            self.last_activity = time.time()
            # After gratitude, listen for another follow-up
            if follow_up_depth < self.config["pipeline"].get("follow_up", {}).get("max_depth", 1):
                self._listen_for_follow_up(follow_up_depth)
            return

        # Check for stop phrases (match whole words only)
        import re
        lower_text = text.lower().strip()
        for phrase in stop_phrases:
            # Create a regex pattern that matches the phrase as a whole word
            pattern = r'\b' + re.escape(phrase.lower()) + r'\b'
            if re.search(pattern, lower_text):
                info(f"Follow-up stopped by phrase: '{phrase}'")
                return

        # Process as follow-up command (skip wake word)
        self.process_command(audio_path=None, skip_wake_word=True, follow_up_depth=follow_up_depth + 1, pre_transcribed_text=text)

