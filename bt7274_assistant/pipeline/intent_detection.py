"""Intent detection helpers for pilot commands."""

import re
from typing import Optional


class IntentDetectionMixin:
    """Mixin for detecting pilot command intents from transcribed text."""

    def _extract_location_from_query(self, text: str) -> Optional[str]:
        """Extract location from weather query like 'weather in Tucson, Arizona'."""
        import re
        lower = text.lower()
        # Match patterns like "weather in X", "weather for X", "temperature in X"
        # Exclude common time words/phrases that shouldn't be treated as locations
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
                # Don't treat time words as locations
                if location in time_words:
                    return None
                # Don't treat multi-word time phrases as locations
                if any(tw in location for tw in time_words):
                    return None
                # If "location" is more than 5 words, it's probably not a real location
                if len(location.split()) > 5:
                    return None
                return location
        return None

    def _is_weather_query(self, text: str) -> bool:
        """Detect if the user is asking for weather."""
        return any(kw in text.lower() for kw in ["weather", "temperature", "forecast"])

    def _is_forecast_query(self, text: str) -> bool:
        """Detect if the user is asking for a forecast (upcoming weather)."""
        lower = text.lower()
        forecast_keywords = [
            "forecast", "later today", "tomorrow", "next week", "next few days",
            "upcoming", "will it rain", "will it snow", "weekend weather",
            "this weekend", "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday", "next day", "in a few days"
        ]
        return any(kw in lower for kw in forecast_keywords)

    def _is_location_query(self, text: str) -> bool:
        """Detect if the user is asking for their location."""
        lower = text.lower().strip()
        location_phrases = ["my location", "where am i", "where are we", "find my location", "what is my location"]
        return any(kw in lower for kw in location_phrases)

    def _is_time_query(self, text: str) -> bool:
        """Detect if the user is asking for the time/date."""
        lower = text.lower().strip()
        time_keywords = ["what time", "what is the time", "current time", "what date", "what is the date", "today's date", "the date today", "what day", "what day is it"]
        return any(kw in lower for kw in time_keywords)

    def _is_status_query(self, text: str) -> bool:
        """Detect if the user is asking for BT-7274's status."""
        lower = text.lower().strip()
        status_keywords = [
            "what is your status", "what's your status", "how are you", "how are you doing",
            "status report", "systems check", "systems status", "are you operational",
            "are you online", "are you functional", "how are your systems",
            "are you okay", "are you alright", "status update", "condition report"
        ]
        return any(kw in lower for kw in status_keywords)

    def _is_vpn_status_query(self, text: str) -> bool:
        """Detect if the user is asking for VPN / cloak status."""
        lower = text.lower().strip()
        vpn_keywords = [
            "vpn status", "cloak status", "are you cloaked", "is the cloak on",
            "is the vpn on", "is vpn connected", "is proton connected",
            "vpn state", "cloak state", "network security", "are we protected",
            "is the network secure", "am i protected", "is my connection secure"
        ]
        return any(kw in lower for kw in vpn_keywords)

    def _is_search_query(self, text: str) -> bool:
        """Detect if the user is asking for real-time info that needs a web search."""
        lower = text.lower()

        # Don't treat weather queries as search queries
        if self._is_weather_query(text):
            return False

        # Don't treat VPN/cloak commands as search queries
        if self._is_vpn_toggle_command(text):
            return False

        # Don't treat todo/note commands as search queries
        if self._is_todo_command(text) or self._is_note_command(text):
            return False

        # Don't treat maintenance commands as search queries
        if self._is_maintenance_command(text):
            return False

        search_keywords = [
            "who won", "who was",
            "news", "latest",
            "search", "look up", "tell me about", "find"
        ]
        
        # Check for basic search keywords (use word boundaries to avoid false matches)
        if any(kw in lower for kw in search_keywords):
            return True
            
        # Check for event/datetime questions that likely need current info
        event_keywords = ["when is", "when was", "what year", "what date", "next", "upcoming", "recent", "price", "cost", "ticket", "how much", "order"]
        has_event_keyword = any(kw in lower for kw in event_keywords)
        
        # Check for specific topics that change over time
        time_sensitive_topics = ["comic con", "conference", "event", "concert", "festival", "tournament", "election", "release", "show"]
        has_time_sensitive_topic = any(topic in lower for topic in time_sensitive_topics)
        
        # If asking about when something happens and it's time-sensitive, it needs search
        if has_event_keyword and has_time_sensitive_topic:
            return True
            
        # Also check for general event information queries
        if self._is_event_information_query(text):
            return True
            
        return False

    def _is_travel_query(self, text: str) -> bool:
        """Detect if the user is asking about travel or transportation."""
        # More specific travel keywords that won't match casual phrases like "go to school"
        travel_keywords = [
            "how to get", "how do i get", "travel to", "transport to",
            "route to", "directions to", "getting to", "trip to",
            "journey to", "commute to", "drive to", "fly to",
            "how do we get", "how to reach", "how can i get",
            "options to get to", "best way to get", "fastest way to get", "how do i reach",
            "how far is", "how long to get to"
        ]
        lower = text.lower()
        
        # Don't treat event information queries as travel queries
        if self._is_event_information_query(text):
            return False
        
        # Don't treat todo commands as travel queries
        if self._is_todo_command(text):
            return False
            
        return any(kw in lower for kw in travel_keywords)

    def _is_travel_query_complex(self, text: str) -> bool:
        """Detect if the user is asking about travel in a complex query."""
        lower = text.lower()
        
        # Don't treat event information queries as travel queries
        if self._is_event_information_query(text):
            return False
        
        # Don't treat todo commands as travel queries
        if self._is_todo_command(text):
            return False
        
        # Check for travel-related words combined with destinations
        travel_indicators = ["how", "way", "route", "travel", "journey"]
        has_travel_word = any(indicator in lower for indicator in travel_indicators)
        
        # Check if asking about getting somewhere specific
        getting_indicators = ["to brussels", "to antwerp", "to belgium", "getting to"]
        has_getting_phrase = any(phrase in lower for phrase in getting_indicators)
        
        return has_travel_word and has_getting_phrase

    def _mentions_destination(self, text: str) -> bool:
        """Detect if the user is mentioning getting to a specific destination."""
        # Don't treat todo commands as travel queries
        if self._is_todo_command(text):
            return False
        
        # Common destinations that people ask about
        destinations = [
            "brussels", "belgium", "paris", "london", "berlin", "amsterdam",
            "madrid", "rome", "vienna", "prague", "budapest", "warsaw",
            "cologne", "hamburg", "munich", "frankfurt", "milan", "barcelona",
            "lisbon", "athens", "stockholm", "copenhagen", "oslo", "helsinki",
            "comic con", "expo", "conference", "event"
        ]
        lower = text.lower()
        return any(dest in lower for dest in destinations)

    def _is_requesting_travel_options(self, text: str) -> bool:
        """Detect if the user is specifically asking for travel options from their location."""
        # Don't treat event information queries as travel queries
        if self._is_event_information_query(text):
            return False
        
        # Don't treat todo commands as travel queries
        if self._is_todo_command(text):
            return False
        
        # Check for combinations of travel-related words and destination mentions
        travel_indicators = ["how", "options", "ways", "methods", "best way", "fastest way"]
        location_indicators = ["from my location", "from here", "from my house", "from my home", "from my current location"]
        
        lower = text.lower()
        has_travel_indicator = any(indicator in lower for indicator in travel_indicators)
        has_location_indicator = any(indicator in lower for indicator in location_indicators)
        
        # Also check for direct questions about getting somewhere
        is_direct_question = any(phrase in lower for phrase in [
            "how do i get to", "how to get to", "options to get to", 
            "ways to get to", "best way to get to", "fastest way to get to"
        ])
        
        return (has_travel_indicator and has_location_indicator) or is_direct_question

    def _is_expression_of_gratitude(self, text: str) -> bool:
        """Detect if the user is expressing gratitude."""
        gratitude_expressions = [
            "thank you", "thanks", "thx", "ty", "appreciate it", 
            "much appreciated", "grateful", "great thanks", "cool thanks"
        ]
        lower = text.lower().strip()
        # Check for exact matches or phrases that start with gratitude expressions
        for expr in gratitude_expressions:
            if lower == expr or lower.startswith(expr + " ") or lower.endswith(" " + expr) or f" {expr} " in lower:
                return True
        return False

    def _is_event_information_query(self, text: str) -> bool:
        """Detect if the user is asking for event information (dates, prices, etc.)"""
        lower = text.lower()
        # Keywords that indicate the user wants information rather than travel
        information_keywords = ["when", "price", "cost", "ticket", "how much", "date", "time", "order"]
        # Topics that are often events
        event_topics = ["comic con", "concert", "festival", "conference", "expo", "event", "show"]
        
        has_info_keyword = any(keyword in lower for keyword in information_keywords)
        has_event_topic = any(topic in lower for topic in event_topics)
        
        return has_info_keyword and has_event_topic

    def _is_todo_command(self, text: str) -> bool:
        """Detect if the user is giving a todo/task command."""
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
        """Detect if the user is giving a note command."""
        lower = text.lower()
        note_phrases = [
            "add note", "make note", "write note", "take note",
            "list notes", "show notes", "read notes", "view notes"
        ]
        return any(phrase in lower for phrase in note_phrases)

    def _is_vpn_toggle_command(self, text: str) -> bool:
        """Detect if the user is asking to turn VPN/cloak on or off."""
        lower = text.lower()
        # Turn on / enable / put on / activate
        on_phrases = [
            "turn on the vpn", "turn on vpn", "turn on cloak", "turn on the cloak",
            "enable vpn", "enable cloak", "enable the vpn", "enable the cloak",
            "put on cloak", "put on the cloak", "put on vpn", "put on the vpn",
            "activate vpn", "activate cloak", "activate the vpn", "activate the cloak",
            "start vpn", "start cloak", "start the vpn", "start the cloak",
            "engage cloak", "engage vpn", "engage the cloak", "engage the vpn",
            "cloak on", "vpn on"
        ]
        # Turn off / disable / take off / deactivate
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
        """Detect if the user is giving a protocol mode command."""
        lower = text.lower()
        protocol_phrases = [
            "protocol brief", "enable protocol mode", "turn on protocol mode",
            "activate protocol mode", "disable protocol mode", "turn off protocol mode",
            "deactivate protocol mode"
        ]
        return any(phrase in lower for phrase in protocol_phrases)

    def _is_maintenance_command(self, text: str) -> bool:
        """Detect if the user is giving a maintenance/system command."""
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

    def _is_log_command(self, text: str) -> bool:
        """Detect if the user is giving a log-related command.

        Uses flexible regex matching to handle variations like
        "make a personal log", "read all of my logs", etc.
        """
        import re
        lower = text.lower()
        # Flexible patterns that allow words between key terms
        log_patterns = [
            # Read/view/show logs - allow any words between
            r"\b(read|view|show|check|see|open)\b.*\b(logs?|entries?)\b",
            r"\bwhat\b.*\b(logs?|entries?)\b",
            r"\b(my|the|bt|system|personal)\b.*\b(logs?|entries?)\b",
            # Make/create logs - allow any words between
            r"\b(make|create|write|add|save|record)\b.*\b(log|entry|note)\b",
            r"\blog\b.*\b(this|that|it)\b",
            # Delete/clear logs - allow any words between
            r"\b(delete|clear|remove|erase|wipe)\b.*\b(logs?|entries?)\b",
        ]
        return any(re.search(pattern, lower) for pattern in log_patterns)

