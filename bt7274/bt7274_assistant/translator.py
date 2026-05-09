"""Translation module for BT-7274.

Provides real-time bidirectional translation for the Pilot.
Uses the LLM for translation with automatic language detection.
Supports translation sessions where BT listens, translates, and facilitates
back-and-forth conversation between the Pilot and a foreign speaker.
"""

import re
import time
from typing import Optional, Dict, Tuple
from dataclasses import dataclass, field

from bt7274.bt7274_assistant.ui import info, status, warning, error, quote


@dataclass
class TranslationSession:
    """Tracks the state of an active translation session."""
    source_lang: str = ""           # Language being translated FROM (foreign)
    target_lang: str = "English"    # Language being translated TO (Pilot's)
    active: bool = False
    auto_detect: bool = True        # Auto-detect source language
    last_foreign_text: str = ""
    last_translated_text: str = ""
    session_start: float = field(default_factory=time.time)
    exchange_count: int = 0

    def to_dict(self) -> dict:
        return {
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "active": self.active,
            "auto_detect": self.auto_detect,
            "last_foreign_text": self.last_foreign_text,
            "last_translated_text": self.last_translated_text,
            "session_start": self.session_start,
            "exchange_count": self.exchange_count,
        }


class TranslatorTool:
    """Translation tool for BT-7274.

    Uses the LLM client for high-quality translation with context awareness.
    Supports both single-shot translation and session-based back-and-forth.
    """

    # Common language names and their ISO-639-1 codes
    LANGUAGE_MAP: Dict[str, str] = {
        "english": "en",
        "spanish": "es",
        "french": "fr",
        "german": "de",
        "italian": "it",
        "portuguese": "pt",
        "dutch": "nl",
        "russian": "ru",
        "chinese": "zh",
        "japanese": "ja",
        "korean": "ko",
        "arabic": "ar",
        "hindi": "hi",
        "turkish": "tr",
        "polish": "pl",
        "swedish": "sv",
        "norwegian": "no",
        "danish": "da",
        "finnish": "fi",
        "greek": "el",
        "czech": "cs",
        "hungarian": "hu",
        "romanian": "ro",
        "ukrainian": "uk",
        "vietnamese": "vi",
        "thai": "th",
        "indonesian": "id",
        "malay": "ms",
        "hebrew": "he",
        "persian": "fa",
        "urdu": "ur",
        "tagalog": "tl",
        "swahili": "sw",
        "catalan": "ca",
        "croatian": "hr",
        "serbian": "sr",
        "slovak": "sk",
        "slovenian": "sl",
        "bulgarian": "bg",
        "lithuanian": "lt",
        "latvian": "lv",
        "estonian": "et",
        "icelandic": "is",
        "welsh": "cy",
        "irish": "ga",
        "scottish": "gd",
        "basque": "eu",
        "galician": "gl",
        "luxembourgish": "lb",
        "maltese": "mt",
        "macedonian": "mk",
        "albanian": "sq",
        "bosnian": "bs",
        "montenegrin": "me",
        "belarusian": "be",
        "georgian": "ka",
        "armenian": "hy",
        "azerbaijani": "az",
        "kazakh": "kk",
        "uzbek": "uz",
        "kyrgyz": "ky",
        "tajik": "tg",
        "turkmen": "tk",
        "mongolian": "mn",
        "nepali": "ne",
        "sinhala": "si",
        "bengali": "bn",
        "tamil": "ta",
        "telugu": "te",
        "kannada": "kn",
        "malayalam": "ml",
        "marathi": "mr",
        "gujarati": "gu",
        "punjabi": "pa",
        "odia": "or",
        "assamese": "as",
        "burmese": "my",
        "khmer": "km",
        "lao": "lo",
        "tibetan": "bo",
        "dzongkha": "dz",
        "pashto": "ps",
        "kurdish": "ku",
        "sorani": "ckb",
        "balochi": "bal",
        "sindhi": "sd",
        "kashmiri": "ks",
        "dogri": "doi",
        "konkani": "kok",
        "manipuri": "mni",
        "santali": "sat",
        "maithili": "mai",
        "sanskrit": "sa",
        "latin": "la",
        "esperanto": "eo",
        "klingon": "tlh",
        "quenya": "qya",
        "sindarin": "sjn",
        "na'vi": "na",
        "dothraki": "art-x-dtk",
        "high valyrian": "art-x-hva",
    }

    # Reverse map for code -> name
    CODE_TO_NAME: Dict[str, str] = {v: k.title() for k, v in LANGUAGE_MAP.items()}

    def __init__(self, llm_client=None):
        self.llm = llm_client
        self.session = TranslationSession()

    def _get_llm(self):
        """Get the LLM client, raising if unavailable."""
        if self.llm is None:
            raise RuntimeError("Translator requires an LLM client. Initialize BT-7274 first.")
        return self.llm

    def _normalize_language(self, lang: str) -> str:
        """Normalize a language name or code to a canonical name."""
        lang_lower = lang.lower().strip()
        # Direct name match
        if lang_lower in self.LANGUAGE_MAP:
            code = self.LANGUAGE_MAP[lang_lower]
            return self.CODE_TO_NAME.get(code, lang_lower.title())
        # Code match
        if lang_lower in self.CODE_TO_NAME:
            return self.CODE_TO_NAME[lang_lower]
        # Partial match
        for name, code in self.LANGUAGE_MAP.items():
            if lang_lower in name or name in lang_lower:
                return self.CODE_TO_NAME.get(code, name.title())
        return lang.strip().title()

    def detect_language(self, text: str) -> str:
        """Detect the language of the given text using the LLM.

        Returns the canonical language name (e.g., 'Spanish', 'Japanese').
        """
        if not text or not text.strip():
            return "Unknown"

        prompt = (
            f"Detect the language of this text. Respond with ONLY the language name, nothing else.\n\n"
            f"Text: \"{text}\"\n\nLanguage:"
        )
        try:
            result = self._get_llm().chat(prompt)
            # Clean up the response
            result = result.strip().strip('"').strip("'")
            # Remove any extra text, keep only the first line/word
            result = result.split('\n')[0].split('.')[0].strip()
            return self._normalize_language(result)
        except Exception as e:
            warning(f"Language detection failed: {e}")
            return "Unknown"

    def translate(self, text: str, source_lang: Optional[str] = None, target_lang: Optional[str] = None) -> Tuple[str, str, str]:
        """Translate text from source language to target language.

        Args:
            text: The text to translate.
            source_lang: Source language name (auto-detected if None).
            target_lang: Target language name (defaults to English).

        Returns:
            Tuple of (translated_text, detected_source_lang, target_lang)
        """
        if not text or not text.strip():
            return "", "Unknown", target_lang or "English"

        # Auto-detect source language if not provided
        if source_lang is None or source_lang.lower() in ("auto", "unknown", ""):
            detected = self.detect_language(text)
            source_lang = detected
        else:
            source_lang = self._normalize_language(source_lang)

        target_lang = self._normalize_language(target_lang or "English")

        # If source and target are the same, return as-is
        if source_lang.lower() == target_lang.lower():
            return text, source_lang, target_lang

        prompt = (
            f"Translate the following text from {source_lang} to {target_lang}.\n"
            f"Preserve meaning, tone, and context. Respond with ONLY the translation, no explanations.\n\n"
            f"Text: \"{text}\"\n\nTranslation:"
        )

        try:
            result = self._get_llm().chat(prompt)
            # Clean up: remove quotes if the LLM wrapped the output
            result = result.strip()
            if result.startswith('"') and result.endswith('"'):
                result = result[1:-1]
            if result.startswith("'") and result.endswith("'"):
                result = result[1:-1]
            return result, source_lang, target_lang
        except Exception as e:
            error(f"Translation failed: {e}")
            return f"[Translation error: {e}]", source_lang, target_lang

    def start_session(self, source_lang: Optional[str] = None, target_lang: str = "English", auto_detect: bool = True) -> str:
        """Start a new translation session.

        Args:
            source_lang: The foreign language to translate from.
            target_lang: The Pilot's language (default English).
            auto_detect: Whether to auto-detect the source language.

        Returns:
            BT-style status message.
        """
        self.session = TranslationSession(
            source_lang=self._normalize_language(source_lang) if source_lang else "",
            target_lang=self._normalize_language(target_lang),
            active=True,
            auto_detect=auto_detect,
        )

        src = self.session.source_lang or "Auto-detect"
        tgt = self.session.target_lang
        return f"Translation protocol active. {src} to {tgt}. I am listening, Pilot."

    def end_session(self) -> str:
        """End the current translation session."""
        if not self.session.active:
            return "No active translation session, Pilot."

        exchanges = self.session.exchange_count
        self.session.active = False
        self.session.source_lang = ""
        self.session.target_lang = "English"
        self.session.last_foreign_text = ""
        self.session.last_translated_text = ""

        return f"Translation protocol disengaged. {exchanges} exchanges logged."

    def is_session_active(self) -> bool:
        """Check if a translation session is currently active."""
        return self.session.active

    def translate_incoming(self, foreign_text: str) -> Tuple[str, str]:
        """Translate foreign speech TO the Pilot's language.

        This is used when BT hears someone speaking a foreign language
        and needs to tell the Pilot what it means.

        Returns:
            Tuple of (translation, bt_response_text)
        """
        if not self.session.active:
            # Auto-start a session with auto-detect
            self.start_session(auto_detect=True)

        source = self.session.source_lang if self.session.source_lang else None
        target = self.session.target_lang

        translated, detected_src, _ = self.translate(foreign_text, source_lang=source, target_lang=target)

        # Update session state
        if not self.session.source_lang and detected_src != "Unknown":
            self.session.source_lang = detected_src
        self.session.last_foreign_text = foreign_text
        self.session.last_translated_text = translated
        self.session.exchange_count += 1

        # Build BT's response
        src_display = self.session.source_lang or detected_src
        bt_response = f"{src_display}: \"{foreign_text}\". Translation: \"{translated}\"."

        return translated, bt_response

    def translate_outgoing(self, pilot_text: str) -> Tuple[str, str]:
        """Translate the Pilot's speech TO the foreign language.

        This is used when the Pilot responds and BT needs to translate
        it back for the foreign speaker.

        Returns:
            Tuple of (translation, bt_response_text)
        """
        if not self.session.active:
            return pilot_text, "No active translation session, Pilot. Say 'start translating' first."

        source = self.session.target_lang
        target = self.session.source_lang if self.session.source_lang else None

        if target is None:
            # Try to detect from the pilot text (unlikely to be foreign, but handle it)
            target = self.detect_language(pilot_text)
            if target.lower() == source.lower():
                # If pilot is speaking their native language, we need a target
                return pilot_text, "Target language not set, Pilot. Specify a language first."

        translated, _, _ = self.translate(pilot_text, source_lang=source, target_lang=target)

        self.session.last_foreign_text = translated
        self.session.last_translated_text = pilot_text
        self.session.exchange_count += 1

        tgt_display = self.session.source_lang or target
        bt_response = f"Translated to {tgt_display}: \"{translated}\"."

        return translated, bt_response

    def get_session_status(self) -> str:
        """Get a status summary of the current translation session."""
        if not self.session.active:
            return "Translation protocol is offline."

        src = self.session.source_lang or "Auto-detect"
        tgt = self.session.target_lang
        exchanges = self.session.exchange_count
        duration = int(time.time() - self.session.session_start)

        return (
            f"Translation protocol active. {src} to {tgt}. "
            f"{exchanges} exchanges, {duration}s elapsed."
        )

    def set_languages(self, source_lang: Optional[str] = None, target_lang: Optional[str] = None) -> str:
        """Update the source and/or target languages for the current session."""
        if source_lang:
            self.session.source_lang = self._normalize_language(source_lang)
        if target_lang:
            self.session.target_lang = self._normalize_language(target_lang)

        src = self.session.source_lang or "Auto-detect"
        tgt = self.session.target_lang
        return f"Languages updated. {src} to {tgt}."

    @classmethod
    def list_supported_languages(cls) -> list[str]:
        """Return a list of supported language names."""
        return sorted([name.title() for name in cls.LANGUAGE_MAP.keys()])
