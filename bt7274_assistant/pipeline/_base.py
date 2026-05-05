"""Base stub class for pipeline mixins to satisfy type checkers."""

from typing import Any


class _AssistantBase:
    """Stub providing attribute declarations shared across all pipeline mixins.

    This avoids circular imports between core.py and the mixin modules while
    giving Pylance enough information to resolve attribute accesses.
    """

    # Config / runtime state
    config: dict[str, Any] = {}
    ai_mode: str = "local"
    performance_mode: Any = None
    console_chat_mode: bool = False
    running: bool = False
    session_id: str = ""
    session_start_time: float = 0.0
    interaction_count: int = 0
    pilot_trust_level: int = 1
    last_activity: float = 0.0

    # Subsystems
    stt: Any = None
    llm: Any = None
    tts: Any = None
    actions: Any = None
    location: Any = None
    recorder: Any = None
    translator: Any = None
    perception: Any = None
    vpn: Any = None
    weather: Any = None
    battery: Any = None
    protocol_brief: Any = None
    logger: Any = None
    voice_telemetry: Any = None

    # Clip / semantic data
    bt_clips: dict[str, str] = {}
    bt_clip_texts: dict[str, str] = {}
    standby_clips: dict[str, str] = {}
    semantic_vectorizer: Any = None
    semantic_clip_matrix: Any = None
    semantic_clip_phrases: list[str] = []

    # Context / dialogue
    conversation_history: list[Any] = []
    current_context: dict[str, Any] = {}
    dialogue_state: str = "idle"
    dialogue_history: list[Any] = []
    personality_weights: dict[str, float] = {}

    # Error tracking
    errors_this_interaction: list[Any] = []
    errors_this_session: list[Any] = []

    # Protocol cooldown
    _last_protocol_reference: Any = None
    _protocol_cooldown_until: float = 0.0
    _protocol_cooldown_seconds: float = 30.0

    # Autonomous logging
    autonomous_log_enabled: bool = False
    autonomous_log_cooldown_until: float = 0.0
    autonomous_logs_this_session: int = 0
    autonomous_log_max_per_session: int = 10
    autonomous_log_cooldown_seconds: float = 60.0
    _last_autonomous_log_hash: str = ""
    actions_this_session: list[str] = []

    # Match tracking
    _last_match_type: Any = None
    _last_match_score: Any = None

    # Cross-mixin method stubs (defined in sibling mixins or core.py)
    def _normalize_phrase(self, phrase: str) -> str:
        return phrase

    def _select_dynamic_clip(self, response_text: str, context: Any = None) -> Any:
        return None

    def _report_error(self, component: str, function: str, exc: Exception, context: Any = None) -> None:
        pass

    def _get_context_aware_phrases(self) -> list[str]:
        return []

    def _get_emotion_matching_phrases(self, text: str) -> list[str]:
        return []

    def _apply_personality_weights(self, phrases: list[str], response_text: str) -> list[tuple[str, float]]:
        return [(p, 1.0) for p in phrases]

    def _update_personality_weights(self, interaction_type: str = "neutral") -> None:
        pass

    def _get_dialogue_response(self, user_input: str, current_state: str = "idle") -> Any:
        return None

    def _update_conversation_context(self, user_query: str, bot_response: str) -> None:
        pass

    def _extract_topics(self, text: str) -> set[str]:
        return set()

    def _detect_emotional_tone(self, text: str) -> str:
        return "neutral"

    def _extract_location_from_query(self, text: str) -> Any:
        return None

    def _is_forecast_query(self, text: str) -> bool:
        return False

    def _is_vpn_toggle_command(self, text: str) -> bool:
        return False

    def _is_todo_command(self, text: str) -> bool:
        return False

    def _is_note_command(self, text: str) -> bool:
        return False

    def _is_weather_query(self, text: str) -> bool:
        return False

    def _is_time_query(self, text: str) -> bool:
        return False

    def _is_location_query(self, text: str) -> bool:
        return False

    def _is_status_query(self, text: str) -> bool:
        return False

    def _is_vpn_status_query(self, text: str) -> bool:
        return False

    def _is_search_query(self, text: str) -> bool:
        return False

    def _is_travel_query(self, text: str) -> bool:
        return False

    def _is_protocol_command(self, text: str) -> bool:
        return False

    def _is_maintenance_command(self, text: str) -> bool:
        return False

    def _is_expression_of_gratitude(self, text: str) -> bool:
        return False

    def _is_vision_query(self, text: str) -> bool:
        return False

    def _is_vision_log_query(self, text: str) -> bool:
        return False

    def _is_translate_command(self, text: str) -> bool:
        return False

    def _is_translate_stop_command(self, text: str) -> bool:
        return False

    def _is_translate_status_command(self, text: str) -> bool:
        return False

    def _is_in_translation_session(self, text: str, translator_active: bool) -> bool:
        return False

    def _extract_translate_language(self, text: str) -> Any:
        return None

    def _is_event_information_query(self, text: str) -> bool:
        return False

    def _mentions_destination(self, text: str) -> bool:
        return False

    def _is_requesting_travel_options(self, text: str) -> bool:
        return False

    def _is_travel_query_complex(self, text: str) -> bool:
        return False

    def _is_log_command(self, text: str) -> bool:
        return False

    def _get_log_clip(self, action: str = "read") -> Any:
        return None

    def _get_status_response_clip(self) -> Any:
        return None

    def _get_system_status_summary(self) -> str:
        return ""

    def _play_bt_clip_with_tts_followup(self, clip_search_text: str, tts_text: str) -> dict:
        return {}

    def clear_tts_cache(self) -> None:
        pass

    def load_config(self, path: str) -> dict:
        return {}

    def _ensure_log_directories(self) -> None:
        pass

    def initialize(self) -> None:
        pass

    def run(self) -> None:
        pass

    def _shutdown(self) -> None:
        pass

    def _save_session_state(self) -> None:
        pass
