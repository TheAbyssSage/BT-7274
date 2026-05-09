#!/usr/bin/env python3
"""
Test script for recently added BT-7274 features and fixes.
Run with: python test_recent_features.py
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import re


class FeatureTester:
    """Test the recently added command detection features."""

    def __init__(self):
        self.passed = 0
        self.failed = 0

    def _normalize_phrase(self, phrase: str) -> str:
        phrase = phrase.lower().strip()
        phrase = re.sub(r'[^\w\s]', '', phrase)
        phrase = re.sub(r'\s+', ' ', phrase)
        return phrase

    def _is_todo_command(self, text: str) -> bool:
        lower = text.lower()
        todo_phrases = [
            "add todo", "add task", "new task", "new todo",
            "add to my to do", "add to my todo", "add to the todo",
            "put on my to do", "put on my todo", "put on the todo",
            "put on to do list", "put on todo list",
            "add to do list", "add todo list",
            "list tasks", "list todos", "show tasks", "show todos", "what are my tasks",
            "clear completed", "clear done tasks"
        ]
        return any(phrase in lower for phrase in todo_phrases)

    def _is_note_command(self, text: str) -> bool:
        lower = text.lower()
        note_phrases = [
            "add note", "make note", "write note", "take note",
            "list notes", "show notes", "read notes", "view notes"
        ]
        return any(phrase in lower for phrase in note_phrases)

    def _is_vpn_toggle_command(self, text: str) -> bool:
        lower = text.lower()
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
        return any(phrase in lower for phrase in on_phrases + off_phrases)

    def _is_protocol_command(self, text: str) -> bool:
        lower = text.lower()
        protocol_phrases = [
            "protocol brief", "enable protocol mode", "turn on protocol mode",
            "activate protocol mode", "disable protocol mode", "turn off protocol mode",
            "deactivate protocol mode"
        ]
        return any(phrase in lower for phrase in protocol_phrases)

    def _is_maintenance_command(self, text: str) -> bool:
        lower = text.lower()
        maintenance_phrases = [
            "clear tts cache", "clear cache",
            "turn on weather warnings", "enable weather warnings",
            "turn on environmental warnings", "enable environmental warnings",
            "turn off weather warnings", "disable weather warnings",
            "turn off environmental warnings", "disable environmental warnings",
            "enable auto cloak", "turn on auto cloak", "enable auto-cloak", "turn on auto-cloak",
            "enable vpn auto connect", "turn on vpn auto connect",
            "disable auto cloak", "turn off auto cloak", "disable auto-cloak", "turn off auto-cloak",
            "disable vpn auto connect", "turn off vpn auto connect",
            "enable vpn monitor", "turn on vpn monitor", "enable cloak monitor", "turn on cloak monitor",
            "disable vpn monitor", "turn off vpn monitor", "disable cloak monitor", "turn off cloak monitor"
        ]
        return any(phrase in lower for phrase in maintenance_phrases)

    def _extract_location_from_query(self, text: str) -> str | None:
        lower = text.lower()
        time_words = {
            "today", "tomorrow", "yesterday", "now", "tonight", "next week", "this week",
            "next few days", "the rest of the day", "rest of the day", "rest of the week",
            "this morning", "this afternoon", "this evening", "later", "soon",
            "all day", "all week", "whole day", "whole week"
        }
        patterns = [
            r'weather\s+(?:in|for|at|near)\s+(.+?)(?:\?|$)',
            r'temperature\s+(?:in|for|at|near)\s+(.+?)(?:\?|$)',
            r'forecast\s+(?:in|for|at|near)\s+(.+?)(?:\?|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, lower)
            if match:
                location = match.group(1).strip()
                if location in time_words:
                    return None
                if any(tw in location for tw in time_words):
                    return None
                if len(location.split()) > 5:
                    return None
                return location
        return None

    def _is_expression_of_gratitude(self, text: str) -> bool:
        gratitude_expressions = [
            "thank you", "thanks", "thx", "ty", "appreciate it",
            "much appreciated", "grateful", "great thanks", "cool thanks"
        ]
        lower = text.lower().strip()
        for expr in gratitude_expressions:
            if lower == expr or lower.startswith(expr + " ") or lower.endswith(" " + expr) or f" {expr} " in lower:
                return True
        return False

    def test(self, name: str, condition: bool):
        if condition:
            print(f"  ✅ PASS: {name}")
            self.passed += 1
        else:
            print(f"  ❌ FAIL: {name}")
            self.failed += 1

    def run_all_tests(self):
        print("=" * 60)
        print("BT-7274 Recent Features Test Suite")
        print("=" * 60)

        # ─── Todo Command Detection ───
        print("\n📋 Todo Command Detection")
        self.test("'add todo buy milk'", self._is_todo_command("add todo buy milk"))
        self.test("'add to my to do list go home'", self._is_todo_command("add to my to do list go home"))
        self.test("'put on my todo list call mom'", self._is_todo_command("put on my todo list call mom"))
        self.test("'put on to do list go to school'", self._is_todo_command("put on to do list go to school"))
        self.test("'list tasks'", self._is_todo_command("list tasks"))
        self.test("'clear completed'", self._is_todo_command("clear completed"))
        self.test("NOT 'what is the weather'", not self._is_todo_command("what is the weather"))

        # ─── Note Command Detection ───
        print("\n📝 Note Command Detection")
        self.test("'add note remember this'", self._is_note_command("add note remember this"))
        self.test("'make note about meeting'", self._is_note_command("make note about meeting"))
        self.test("'list notes'", self._is_note_command("list notes"))
        self.test("NOT 'add todo'", not self._is_note_command("add todo"))

        # ─── VPN/Cloak Toggle Detection ───
        print("\n🔒 VPN/Cloak Toggle Detection")
        self.test("'turn on the VPN'", self._is_vpn_toggle_command("turn on the VPN"))
        self.test("'turn on VPN'", self._is_vpn_toggle_command("turn on VPN"))
        self.test("'put on cloak'", self._is_vpn_toggle_command("put on cloak"))
        self.test("'put on the cloak'", self._is_vpn_toggle_command("put on the cloak"))
        self.test("'engage cloak'", self._is_vpn_toggle_command("engage cloak"))
        self.test("'activate the VPN'", self._is_vpn_toggle_command("activate the VPN"))
        self.test("'turn off the cloak'", self._is_vpn_toggle_command("turn off the cloak"))
        self.test("'take off cloak'", self._is_vpn_toggle_command("take off cloak"))
        self.test("'disable VPN'", self._is_vpn_toggle_command("disable VPN"))
        self.test("'disengage the cloak'", self._is_vpn_toggle_command("disengage the cloak"))
        self.test("'cloak off'", self._is_vpn_toggle_command("cloak off"))
        self.test("NOT 'what is a vpn'", not self._is_vpn_toggle_command("what is a vpn"))
        self.test("NOT 'vpn status'", not self._is_vpn_toggle_command("vpn status"))

        # ─── Maintenance Command Detection ───
        print("\n🔧 Maintenance Command Detection")
        self.test("'clear tts cache'", self._is_maintenance_command("clear tts cache"))
        self.test("'turn on auto cloak'", self._is_maintenance_command("turn on auto cloak"))
        self.test("'disable weather warnings'", self._is_maintenance_command("disable weather warnings"))
        self.test("'enable vpn monitor'", self._is_maintenance_command("enable vpn monitor"))
        self.test("NOT 'what is the weather'", not self._is_maintenance_command("what is the weather"))

        # ─── Protocol Command Detection ───
        print("\n📡 Protocol Command Detection")
        self.test("'protocol brief'", self._is_protocol_command("protocol brief"))
        self.test("'enable protocol mode'", self._is_protocol_command("enable protocol mode"))
        self.test("'turn off protocol mode'", self._is_protocol_command("turn off protocol mode"))

        # ─── Location Extraction Fix ───
        print("\n🌍 Location Extraction (Weather)")
        self.test("'weather in Brussels' -> 'brussels'",
                  self._extract_location_from_query("weather in Brussels") == "brussels")
        self.test("'weather for the rest of the day' -> None",
                  self._extract_location_from_query("weather for the rest of the day") is None)
        self.test("'what is the weather for the rest of the day' -> None",
                  self._extract_location_from_query("what is the weather for the rest of the day") is None)
        self.test("'weather in New York City' -> 'new york city'",
                  self._extract_location_from_query("weather in New York City") == "new york city")
        self.test("'weather tomorrow' -> None",
                  self._extract_location_from_query("weather tomorrow") is None)

        # ─── Gratitude Detection ───
        print("\n🙏 Gratitude Detection")
        self.test("'thank you'", self._is_expression_of_gratitude("thank you"))
        self.test("'thanks BT'", self._is_expression_of_gratitude("thanks BT"))
        self.test("'thank you BT. Turn on the VPN.'",
                  self._is_expression_of_gratitude("thank you BT. Turn on the VPN."))
        self.test("NOT 'what is the weather'", not self._is_expression_of_gratitude("what is the weather"))

        # ─── Meta-text Filtering ───
        print("\n🧹 Meta-text Filtering")
        meta_patterns = [
            r'(?i)^\s*bt\s+(?:uses?|initiates?|performs?|executes?|triggers?|activates?|engages?|starts?)\s+.*$',
            r'(?i)^\s*bt\s+(?:is\s+)?(?:now\s+)?(?:using|initiating|performing|executing|triggering|activating|engaging|starting)\s+.*$',
            r'(?i)^\s*(?:simultaneously|meanwhile|at\s+the\s+same\s+time)\s*,?\s*bt\s+.*$',
            r'(?i)^\s*bt\s+(?:also|additionally|furthermore|moreover)\s+.*$',
            r'(?i)^\s*(?:action|system|protocol)\s*:.*$',
        ]
        test_lines = [
            ("BT uses the get_weather action.", True),
            ("BT initiates clearing the cache.", True),
            ("Simultaneously BT engages cloak.", True),
            ("BT also performs a search.", True),
            ("Action: get_weather", True),
            ("The weather is clear today.", False),
            ("Pilot, all systems are operational.", False),
        ]
        for line, should_match in test_lines:
            matches = any(re.match(pattern, line) for pattern in meta_patterns)
            self.test(f"'{line}' -> {'filtered' if should_match else 'kept'}", matches == should_match)

        # ─── Summary ───
        print("\n" + "=" * 60)
        print(f"Results: {self.passed} passed, {self.failed} failed")
        if self.failed == 0:
            print("🎉 All tests passed!")
        else:
            print("⚠️  Some tests failed. Review the output above.")
        print("=" * 60)
        return self.failed == 0


if __name__ == "__main__":
    tester = FeatureTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
