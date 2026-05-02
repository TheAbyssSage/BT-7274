"""BT-7274 original voice clip loading, semantic matching, and dynamic selection."""

import csv
import json
import random
from pathlib import Path
from typing import Optional

import numpy as np

from bt7274_workstation.session_cache_manager import (
    save_semantic_vectors,
    load_semantic_vectors,
)
from ui import success, warning, info, status, loading_bar

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SEMANTIC_SIMILARITY_AVAILABLE = True
except ImportError:
    SEMANTIC_SIMILARITY_AVAILABLE = False
    import logging
    logging.getLogger("BT7274").warning(
        "Semantic similarity matching not available. Install scikit-learn for this feature."
    )


class ClipMatchingMixin:
    """Mixin for BT-7274 original voice clip loading, semantic matching, and dynamic selection."""

    def _normalize_phrase(self, phrase: str) -> str:
        """Normalize a phrase for dictionary lookup."""
        import re
        phrase = phrase.lower().strip()
        phrase = re.sub(r'[^\w\s]', '', phrase)  # remove punctuation
        phrase = re.sub(r'\s+', ' ', phrase)     # collapse spaces
        return phrase

    def _normalize_filename_to_phrase(self, filename: str) -> str:
        """Convert a filename back to its original phrase."""
        # Remove .wav extension
        phrase = filename.replace('.wav', '')
        # Replace underscores with spaces
        phrase = phrase.replace('_', ' ')
        # Handle special cases for common phrases
        phrase = phrase.replace('you re welcome', "you're welcome")
        return phrase.strip()

    def _load_bt_original_clips(self):
        """Load BT-7274's original voice clips from the game for instant responses."""
        import csv
        import json
        voicepack_dir = Path(__file__).parent.parent / "BT-7274.Voicepack"
        bt_clips_dir = voicepack_dir / "bt_clips"
        csv_file = voicepack_dir / "bt_clips_index.csv"
        
        # Try to load precomputed mappings first
        mappings_dir = Path(__file__).parent / "mappings"
        phrases_to_files = mappings_dir / "bt_phrases_to_files.json"
        
        if phrases_to_files.exists():
            try:
                with open(phrases_to_files, 'r') as f:
                    phrase_map = json.load(f)
                loaded = 0
                total = len(phrase_map)
                for i, (phrase, filename) in enumerate(phrase_map.items()):
                    loading_bar("Loading BT voice clips", i, total)
                    wav_path = bt_clips_dir / filename
                    if wav_path.exists():
                        self.bt_clips[phrase] = str(wav_path)
                        self.bt_clip_texts[filename] = phrase
                        loaded += 1
                loading_bar("Loading BT voice clips", total, total)
                success(f"Loaded {loaded} BT-7274 original voice clips from mappings.")
                return
            except Exception as e:
                warning(f"Failed to load precomputed mappings: {e}")
        
        # Fallback to loading from CSV
        if not csv_file.exists():
            warning("BT-7274 original clips CSV not found. Skipping.")
            return
            
        if not bt_clips_dir.exists():
            warning("BT-7274 original clips directory not found. Skipping.")
            return

        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                total = len(rows)
                loaded = 0
                for i, row in enumerate(rows):
                    loading_bar("Loading BT voice clips", i, total)
                    filename = row['filename']
                    text = row['text']
                    wav_path = bt_clips_dir / filename
                    
                    if wav_path.exists():
                        normalized_text = self._normalize_phrase(text)
                        self.bt_clips[normalized_text] = str(wav_path)
                        self.bt_clip_texts[filename] = text
                        loaded += 1
                loading_bar("Loading BT voice clips", total, total)
                success(f"Loaded {loaded} BT-7274 original voice clips from CSV.")
        except Exception as e:
            error(f"Error loading BT-7274 original clips: {e}")

    def _initialize_semantic_matching(self):
        """Initialize semantic similarity matching for BT clips."""
        if not SEMANTIC_SIMILARITY_AVAILABLE:
            return
            
        if not self.bt_clips:
            return
            
        try:
            # Try to load cached semantic vectors first
            vectorizer_state, clip_matrix, phrases = load_semantic_vectors()
            if vectorizer_state is not None and clip_matrix is not None and phrases:
                self.semantic_vectorizer = TfidfVectorizer(**vectorizer_state)
                self.semantic_clip_matrix = clip_matrix
                self.semantic_clip_phrases = phrases
                success(f"Semantic similarity matching loaded from cache with {len(phrases)} phrases")
                return

            # Create TF-IDF vectorizer
            self.semantic_vectorizer = TfidfVectorizer(
                lowercase=True,
                stop_words='english',
                ngram_range=(1, 2),  # Use unigrams and bigrams
                max_features=1000    # Limit vocabulary size
            )
            
            # Get all phrases for semantic matching
            self.semantic_clip_phrases = list(self.bt_clips.keys())
            
            # Fit the vectorizer on all BT clip phrases
            loading_bar("Building semantic index", 1, 2)
            self.semantic_clip_matrix = self.semantic_vectorizer.fit_transform(self.semantic_clip_phrases)
            loading_bar("Building semantic index", 2, 2)
            
            # Persist to session cache
            vectorizer_state = {
                "lowercase": self.semantic_vectorizer.lowercase,
                "stop_words": self.semantic_vectorizer.stop_words,
                "ngram_range": self.semantic_vectorizer.ngram_range,
                "max_features": self.semantic_vectorizer.max_features,
            }
            save_semantic_vectors(vectorizer_state, self.semantic_clip_matrix, self.semantic_clip_phrases)
            
            success(f"Semantic similarity matching initialized with {len(self.semantic_clip_phrases)} phrases")
        except Exception as e:
            warning(f"Failed to initialize semantic similarity matching: {e}")
            self.semantic_vectorizer = None
            self.semantic_clip_matrix = None
            self.semantic_clip_phrases = []

    def _update_conversation_context(self, user_query: str, bot_response: str):
        """Update conversation context with the latest interaction."""
        # Add to conversation history
        self.conversation_history.append((user_query, bot_response))
        
        # Keep only the last 10 interactions to avoid memory issues
        if len(self.conversation_history) > 10:
            self.conversation_history.pop(0)
        
        # Update current context based on keywords
        user_lower = user_query.lower()
        response_lower = bot_response.lower()
        
        # Detect conversation topics - reset to general first, then detect new topic
        detected_topic = "general"
        if any(word in user_lower for word in ["weather", "temperature", "forecast"]):
            detected_topic = "weather"
        elif any(word in user_lower for word in ["time", "date", "clock"]):
            detected_topic = "time"
        elif any(word in user_lower for word in ["location", "where"]):
            detected_topic = "location"
        elif any(word in user_lower for word in ["thank", "thanks", "appreciate"]):
            detected_topic = "gratitude"
        elif any(word in user_lower for word in ["status", "systems", "operational"]):
            detected_topic = "status"
        elif any(word in user_lower for word in ["mission", "objective", "task", "todo"]):
            detected_topic = "mission"
        elif any(word in user_lower for word in ["vpn", "cloak", "network"]):
            detected_topic = "network"
        elif any(word in user_lower for word in ["log", "note", "entry"]):
            detected_topic = "logs"
        
        # Only update topic if we detected something specific or if it was already general
        # This prevents "general" from overwriting a specific topic on follow-ups
        if detected_topic != "general" or self.current_context.get("topic", "general") == "general":
            self.current_context["topic"] = detected_topic
            
        # Detect emotional tone from user
        if any(word in user_lower for word in ["help", "assist", "support"]):
            self.current_context["user_emotion"] = "seeking_help"
        elif any(word in user_lower for word in ["danger", "careful", "warning"]):
            self.current_context["user_emotion"] = "concerned"
        elif any(word in user_lower for word in ["good", "great", "awesome", "perfect"]):
            self.current_context["user_emotion"] = "positive"
        else:
            # Reset user emotion to neutral if no emotional indicators found
            self.current_context["user_emotion"] = "neutral"
            
        # Detect emotional tone from bot response
        if any(word in response_lower for word in ["danger", "careful", "warning", "caution"]):
            self.current_context["bot_emotion"] = "cautious"
        elif any(word in response_lower for word in ["congratulations", "well done", "excellent"]):
            self.current_context["bot_emotion"] = "positive"
        elif any(word in response_lower for word in ["understood", "acknowledged", "copy that"]):
            self.current_context["bot_emotion"] = "neutral"
        else:
            # Reset bot emotion to neutral if no emotional indicators found
            self.current_context["bot_emotion"] = "neutral"

    def _get_context_aware_phrases(self) -> list[str]:
        """Get phrases that match the current conversation context."""
        context_phrases = []
        
        # Get current topic
        topic = self.current_context.get("topic", "")
        
        # Define context-specific keywords for BT clips
        context_keywords = {
            "weather": ["weather", "atmospheric", "sensors", "storm", "rain", "wind", "temperature"],
            "time": ["time", "chronometer", "clock", "date", "calendar"],
            "location": ["location", "position", "coordinates", "navigation", "map"],
            "gratitude": ["welcome", "pleasure", "assist", "help", "support"],
            "combat": ["enemy", "hostile", "titan", "weapon", "combat", "attack"],
            "mission": ["mission", "objective", "protocol", "orders", "task"],
            "status": ["status", "condition", "systems", "operational", "functional"]
        }
        
        # Get keywords for current topic
        keywords = context_keywords.get(topic, [])
        
        # Find BT clips that match these keywords
        for phrase, path in self.bt_clips.items():
            if any(keyword in phrase for keyword in keywords):
                context_phrases.append(phrase)
        
        return context_phrases

    def _detect_emotional_tone(self, text: str) -> str:
        """Detect the emotional tone of a text."""
        text_lower = text.lower()
        
        # Define emotional tone indicators
        tone_indicators = {
            "urgent": ["danger", "warning", "alert", "emergency", "critical", "hurry", "quick"],
            "cautious": ["careful", "caution", "beware", "watch out", "attention"],
            "positive": ["good", "great", "excellent", "perfect", "wonderful", "amazing"],
            "concerned": ["worry", "concern", "afraid", "scared", "nervous", "anxious"],
            "determined": ["must", "will", "shall", "determined", "committed", "resolve"],
            "neutral": ["understood", "acknowledged", "copy that", "roger", "affirmative"]
        }
        
        # Count matches for each tone
        tone_scores = {}
        for tone, indicators in tone_indicators.items():
            score = sum(1 for indicator in indicators if indicator in text_lower)
            if score > 0:
                tone_scores[tone] = score
        
        # Return the tone with highest score, or "neutral" if no matches
        if tone_scores:
            return max(tone_scores, key=tone_scores.get)
        return "neutral"

    def _get_emotion_matching_phrases(self, text: str) -> list[str]:
        """Get phrases that match the emotional tone of the text."""
        tone = self._detect_emotional_tone(text)
        
        # Define emotional tone keywords for BT clips
        emotion_keywords = {
            "urgent": ["danger", "warning", "alert", "emergency", "critical", "hurry"],
            "cautious": ["careful", "caution", "beware", "watch out", "attention"],
            "positive": ["good", "great", "excellent", "perfect", "wonderful", "congratulations"],
            "concerned": ["worry", "concern", "careful", "safe", "protect"],
            "determined": ["must", "will", "shall", "determined", "committed", "resolve", "protocol"],
            "neutral": ["understood", "acknowledged", "copy that", "roger", "affirmative", "standing by"]
        }
        
        # Get keywords for detected tone
        keywords = emotion_keywords.get(tone, [])
        
        # Find BT clips that match these emotional keywords
        matching_phrases = []
        for phrase, path in self.bt_clips.items():
            if any(keyword in phrase for keyword in keywords):
                matching_phrases.append(phrase)
        
        return matching_phrases

    def _select_dynamic_clip(self, response_text: str, context: Optional[dict] = None) -> Optional[str]:
        """Dynamically select the best BT clip based on conversation context.
        
        This method combines multiple factors to choose the most appropriate clip:
        1. Exact match priority
        2. Semantic similarity
        3. Context relevance
        4. Emotional tone matching
        5. Conversation history
        """
        if not response_text:
            return None
            
        normalized = self._normalize_phrase(response_text)
        candidates = []
        
        # 1. Exact match (highest priority)
        if normalized in self.bt_clips:
            candidates.append((self.bt_clips[normalized], 1.0, "exact"))
        
        # 2. Semantic similarity matching
        if self.semantic_vectorizer and self.semantic_clip_matrix is not None:
            try:
                response_vector = self.semantic_vectorizer.transform([normalized])
                similarities = cosine_similarity(response_vector, self.semantic_clip_matrix)
                
                # Get top 5 semantic matches
                top_indices = np.argsort(similarities[0])[-5:][::-1]
                for idx in top_indices:
                    similarity = similarities[0][idx]
                    if similarity > 0.3:
                        phrase = self.semantic_clip_phrases[idx]
                        path = self.bt_clips.get(phrase)
                        if path:
                            candidates.append((path, similarity * 0.8, "semantic"))
            except Exception as e:
                warning(f"Semantic matching failed: {e}")
        
        # 3. Context-aware matching
        context_phrases = self._get_context_aware_phrases()
        if context_phrases:
            for phrase in context_phrases:
                if normalized in phrase or phrase in normalized:
                    path = self.bt_clips.get(phrase)
                    if path:
                        candidates.append((path, 0.7, "context"))
        
        # 4. Emotional tone matching
        emotion_phrases = self._get_emotion_matching_phrases(response_text)
        if emotion_phrases:
            for phrase in emotion_phrases:
                if normalized in phrase or phrase in normalized:
                    path = self.bt_clips.get(phrase)
                    if path:
                        candidates.append((path, 0.6, "emotion"))
        
        # 5. Conversation history boost
        if self.conversation_history:
            recent_topics = set()
            for query, resp in self.conversation_history[-3:]:
                recent_topics.update(self._extract_topics(query))
            
            for phrase, path in self.bt_clips.items():
                phrase_topics = self._extract_topics(phrase)
                if recent_topics & phrase_topics:  # Intersection
                    candidates.append((path, 0.5, "history"))
        
        # Remove duplicates while keeping highest score
        seen_paths = {}
        for path, score, match_type in candidates:
            if path not in seen_paths or seen_paths[path][0] < score:
                seen_paths[path] = (score, match_type)
        
        if not seen_paths:
            return None
        
        # Select best candidate
        best_path = max(seen_paths.keys(), key=lambda p: seen_paths[p][0])
        best_score, best_type = seen_paths[best_path]
        
        # Store match info for logging
        self._last_match_type = best_type
        self._last_match_score = round(best_score, 2)
        
        info(f"Dynamic clip selected: {best_type} match (score: {best_score:.2f})")
        return best_path

    def _extract_topics(self, text: str) -> set:
        """Extract topics from text for conversation history matching."""
        text_lower = text.lower()
        topics = set()
        
        topic_keywords = {
            "combat": ["enemy", "titan", "weapon", "attack", "defend", "fight"],
            "mission": ["mission", "objective", "protocol", "orders", "task"],
            "status": ["status", "condition", "systems", "operational"],
            "location": ["location", "position", "coordinates", "navigation"],
            "pilot": ["pilot", "cooper", "jack"],
            "danger": ["danger", "warning", "alert", "emergency"],
            "support": ["help", "assist", "support", "aid"]
        }
        
        for topic, keywords in topic_keywords.items():
            if any(kw in text_lower for kw in keywords):
                topics.add(topic)
        
        return topics

    def _apply_personality_weights(self, phrases: list[str], response_text: str) -> list[tuple[str, float]]:
        """Apply personality-based weighting to phrase candidates.
        
        BT-7274's personality traits:
        - Loyal: Prioritizes pilot safety and trust
        - Formal: Military protocol and proper address
        - Tactical: Mission-focused, strategic thinking
        - Dry humor: Occasional wit, literal interpretations
        """
        weighted_phrases = []
        
        for phrase in phrases:
            weight = 1.0
            phrase_lower = phrase.lower()
            
            # Loyalty weighting - boost phrases that show pilot care
            if self.personality_weights["loyalty"] > 0.5:
                loyalty_indicators = ["pilot", "protect", "safe", "trust", "link"]
                loyalty_score = sum(1 for ind in loyalty_indicators if ind in phrase_lower)
                weight += loyalty_score * self.personality_weights["loyalty"] * 0.2
            
            # Formality weighting - boost protocol and formal language
            if self.personality_weights["formality"] > 0.5:
                formal_indicators = ["protocol", "acknowledged", "confirmed", "standing by", "copy that"]
                formal_score = sum(1 for ind in formal_indicators if ind in phrase_lower)
                weight += formal_score * self.personality_weights["formality"] * 0.15
            
            # Tactical weighting - boost mission and strategic language
            if self.personality_weights["tactical"] > 0.5:
                tactical_indicators = ["mission", "objective", "tactical", "strategic", "analyze"]
                tactical_score = sum(1 for ind in tactical_indicators if ind in phrase_lower)
                weight += tactical_score * self.personality_weights["tactical"] * 0.15
            
            # Humor weighting - boost witty or literal interpretations
            if self.personality_weights["humor"] > 0.3:
                humor_indicators = ["trust me", "i am bt", "vanguard class", "protocol 3"]
                humor_score = sum(1 for ind in humor_indicators if ind in phrase_lower)
                weight += humor_score * self.personality_weights["humor"] * 0.1
            
            # Urgency weighting - depends on detected emotion
            detected_emotion = self._detect_emotional_tone(response_text)
            if detected_emotion == "urgent" and self.personality_weights["urgency"] > 0.5:
                urgency_indicators = ["danger", "warning", "alert", "emergency", "critical"]
                urgency_score = sum(1 for ind in urgency_indicators if ind in phrase_lower)
                weight += urgency_score * self.personality_weights["urgency"] * 0.25
            
            weighted_phrases.append((phrase, weight))
        
        # Sort by weight descending
        weighted_phrases.sort(key=lambda x: x[1], reverse=True)
        return weighted_phrases

    def _update_personality_weights(self, interaction_type: str = "neutral"):
        """Update personality weights based on interaction type and trust level."""
        # Increase loyalty with more interactions
        self.personality_weights["loyalty"] = min(1.0, 0.5 + (self.pilot_trust_level * 0.1))
        
        # Adjust formality based on context
        if interaction_type == "combat":
            self.personality_weights["formality"] = 0.9
            self.personality_weights["urgency"] = 0.9
            self.personality_weights["humor"] = 0.1
        elif interaction_type == "casual":
            self.personality_weights["formality"] = 0.6
            self.personality_weights["urgency"] = 0.3
            self.personality_weights["humor"] = 0.5
        elif interaction_type == "emergency":
            self.personality_weights["formality"] = 0.95
            self.personality_weights["urgency"] = 1.0
            self.personality_weights["humor"] = 0.0
        
        # Tactical remains consistently high
        self.personality_weights["tactical"] = 0.85

    def _build_dialogue_tree(self, root_phrase: Optional[str] = None) -> dict:
        """Build an interactive dialogue tree using original game lines.
        
        Creates a tree structure where each node is a BT clip and edges
        represent logical conversation transitions.
        """
        tree = {
            "root": root_phrase or "protocol 1 link to pilot",
            "nodes": {},
            "edges": {}
        }
        
        # Define dialogue categories and their related phrases
        dialogue_categories = {
            "greeting": [
                "protocol 1 link to pilot",
                "neural link established",
                "you may call me bt",
                "i am bt7274"
            ],
            "status_check": [
                "systems operational",
                "all systems nominal",
                "standing by pilot",
                "ready to proceed"
            ],
            "mission_brief": [
                "our orders are to resume special operation 217",
                "rendezvous with major anderson of the srs",
                "the rendezvous point is 106 clicks northeast"
            ],
            "combat_ready": [
                "weapon systems online",
                "titanfall imminent",
                "engaging enemy titans",
                "defensive protocols active"
            ],
            "pilot_care": [
                "be careful pilot",
                "pilot our location has been compromised",
                "are you alright pilot",
                "i will not lose another pilot"
            ],
            "protocol_statements": [
                "protocol 1 link to pilot",
                "protocol 2 uphold the mission",
                "protocol 3 protect the pilot"
            ]
        }
        
        # Build nodes from available clips
        for category, phrases in dialogue_categories.items():
            tree["nodes"][category] = []
            for phrase in phrases:
                normalized = self._normalize_phrase(phrase)
                if normalized in self.bt_clips:
                    tree["nodes"][category].append({
                        "phrase": phrase,
                        "path": self.bt_clips[normalized],
                        "category": category
                    })
        
        # Define logical transitions between categories
        tree["edges"] = {
            "greeting": ["status_check", "mission_brief"],
            "status_check": ["mission_brief", "combat_ready", "pilot_care"],
            "mission_brief": ["combat_ready", "protocol_statements"],
            "combat_ready": ["pilot_care", "protocol_statements"],
            "pilot_care": ["protocol_statements", "status_check"],
            "protocol_statements": ["greeting", "mission_brief"]
        }
        
        return tree

    def _get_dialogue_response(self, user_input: str, current_state: str = "idle") -> Optional[str]:
        """Get the next response in a dialogue tree based on user input.
        
        Uses keyword matching to determine the most appropriate next line
        in the conversation flow.
        """
        # Build dialogue tree if not already done
        if not hasattr(self, '_dialogue_tree') or self._dialogue_tree is None:
            self._dialogue_tree = self._build_dialogue_tree()
        
        tree = self._dialogue_tree
        user_lower = user_input.lower()
        
        # Determine intent from user input
        intent = self._determine_dialogue_intent(user_input)
        
        # Get available transitions from current state
        if current_state in tree["edges"]:
            possible_categories = tree["edges"][current_state]
        else:
            possible_categories = list(tree["nodes"].keys())
        
        # Find best matching phrase based on intent
        best_match = None
        best_score = 0
        
        for category in possible_categories:
            if category not in tree["nodes"]:
                continue
                
            for node in tree["nodes"][category]:
                phrase = node["phrase"].lower()
                score = 0
                
                # Score based on intent matching
                if intent == "greeting" and category == "greeting":
                    score += 2
                elif intent == "status" and category == "status_check":
                    score += 2
                elif intent == "mission" and category == "mission_brief":
                    score += 2
                elif intent == "combat" and category == "combat_ready":
                    score += 2
                elif intent == "concern" and category == "pilot_care":
                    score += 2
                elif intent == "protocol" and category == "protocol_statements":
                    score += 2
                
                # Score based on keyword overlap
                user_words = set(user_lower.split())
                phrase_words = set(phrase.split())
                overlap = len(user_words & phrase_words)
                score += overlap
                
                if score > best_score:
                    best_score = score
                    best_match = node
        
        if best_match and best_score > 0:
            self.dialogue_state = best_match["category"]
            self.dialogue_history.append(best_match["phrase"])
            status("DIALOGUE", f"Transition: {current_state} -> {best_match['category']}")
            return best_match["path"]
        
        return None

    def _determine_dialogue_intent(self, text: str) -> str:
        """Determine the user's intent for dialogue tree navigation."""
        text_lower = text.lower()
        
        # Greeting intents
        if any(word in text_lower for word in ["hello", "hi", "hey", "greetings", "bt"]):
            return "greeting"
        
        # Status intents
        if any(word in text_lower for word in ["status", "how are you", "systems", "operational"]):
            return "status"
        
        # Mission intents
        if any(word in text_lower for word in ["mission", "objective", "orders", "task", "plan"]):
            return "mission"
        
        # Combat intents
        if any(word in text_lower for word in ["fight", "attack", "defend", "enemy", "weapon", "combat"]):
            return "combat"
        
        # Concern intents
        if any(word in text_lower for word in ["careful", "safe", "protect", "danger", "worry"]):
            return "concern"
        
        # Protocol intents
        if any(word in text_lower for word in ["protocol", "link", "trust", "protocol 1", "protocol 2", "protocol 3"]):
            return "protocol"
        
        return "general"

