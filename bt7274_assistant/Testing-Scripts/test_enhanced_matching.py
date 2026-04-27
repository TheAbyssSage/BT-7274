#!/usr/bin/env python3
"""
Standalone test script for enhanced BT-7274 clip matching features
Tests semantic similarity, context-aware selection, and emotional tone matching
"""

import sys
import csv
import re
import json
from pathlib import Path
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Try to import sklearn
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
    SEMANTIC_SIMILARITY_AVAILABLE = True
except ImportError:
    SEMANTIC_SIMILARITY_AVAILABLE = False
    print("⚠ Semantic similarity matching not available. Install scikit-learn for this feature.")

def normalize_phrase(phrase: str) -> str:
    """Normalize a phrase for dictionary lookup."""
    phrase = phrase.lower().strip()
    phrase = re.sub(r'[^\w\s]', '', phrase)  # remove punctuation
    phrase = re.sub(r'\s+', ' ', phrase)     # collapse spaces
    return phrase

def load_bt_clips():
    """Load BT-7274's original voice clips."""
    voicepack_dir = Path(__file__).parent.parent / "BT-7274.Voicepack"
    bt_clips_dir = voicepack_dir / "bt_clips"
    csv_file = voicepack_dir / "bt_clips_index.csv"
    
    bt_clips = {}
    
    if not csv_file.exists():
        print("⚠ BT-7274 original clips CSV not found.")
        return bt_clips
        
    if not bt_clips_dir.exists():
        print("⚠ BT-7274 original clips directory not found.")
        return bt_clips

    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            loaded = 0
            for row in reader:
                filename = row['filename']
                text = row['text']
                wav_path = bt_clips_dir / filename
                
                if wav_path.exists():
                    normalized_text = normalize_phrase(text)
                    bt_clips[normalized_text] = str(wav_path)
                    loaded += 1
                    
        print(f"✓ Loaded {loaded} BT-7274 original voice clips.")
        return bt_clips
    except Exception as e:
        print(f"✗ Error loading BT-7274 clips: {e}")
        return {}

class EnhancedMatchingTester:
    def __init__(self):
        self.bt_clips = load_bt_clips()
        self.semantic_vectorizer = None
        self.semantic_clip_matrix = None
        self.semantic_clip_phrases = []
        self.current_context = {}
        self.conversation_history = []
        
    def initialize_semantic_matching(self):
        """Initialize semantic similarity matching for BT clips."""
        if not SEMANTIC_SIMILARITY_AVAILABLE:
            print("⚠ Semantic similarity not available (scikit-learn not installed)")
            return False
            
        if not self.bt_clips:
            print("⚠ No BT clips loaded")
            return False
            
        try:
            self.semantic_vectorizer = TfidfVectorizer(
                lowercase=True,
                stop_words='english',
                ngram_range=(1, 2),
                max_features=1000
            )
            
            self.semantic_clip_phrases = list(self.bt_clips.keys())
            self.semantic_clip_matrix = self.semantic_vectorizer.fit_transform(self.semantic_clip_phrases)
            
            print(f"✓ Semantic similarity matching initialized with {len(self.semantic_clip_phrases)} phrases")
            return True
        except Exception as e:
            print(f"⚠ Failed to initialize semantic similarity matching: {e}")
            return False

    def update_conversation_context(self, user_query: str, bot_response: str):
        """Update conversation context with the latest interaction."""
        self.conversation_history.append((user_query, bot_response))
        
        if len(self.conversation_history) > 10:
            self.conversation_history.pop(0)
        
        user_lower = user_query.lower()
        response_lower = bot_response.lower()
        
        if any(word in user_lower for word in ["weather", "temperature", "forecast"]):
            self.current_context["topic"] = "weather"
        elif any(word in user_lower for word in ["time", "date", "clock"]):
            self.current_context["topic"] = "time"
        elif any(word in user_lower for word in ["location", "where"]):
            self.current_context["topic"] = "location"
        elif any(word in user_lower for word in ["thank", "thanks", "appreciate"]):
            self.current_context["topic"] = "gratitude"
            
        if any(word in user_lower for word in ["help", "assist", "support"]):
            self.current_context["user_emotion"] = "seeking_help"
        elif any(word in user_lower for word in ["danger", "careful", "warning"]):
            self.current_context["user_emotion"] = "concerned"
        elif any(word in user_lower for word in ["good", "great", "awesome", "perfect"]):
            self.current_context["user_emotion"] = "positive"
            
        if any(word in response_lower for word in ["danger", "careful", "warning", "caution"]):
            self.current_context["bot_emotion"] = "cautious"
        elif any(word in response_lower for word in ["congratulations", "well done", "excellent"]):
            self.current_context["bot_emotion"] = "positive"
        elif any(word in response_lower for word in ["understood", "acknowledged", "copy that"]):
            self.current_context["bot_emotion"] = "neutral"

    def get_context_aware_phrases(self) -> list:
        """Get phrases that match the current conversation context."""
        context_phrases = []
        topic = self.current_context.get("topic", "")
        
        context_keywords = {
            "weather": ["weather", "atmospheric", "sensors", "storm", "rain", "wind", "temperature"],
            "time": ["time", "chronometer", "clock", "date", "calendar"],
            "location": ["location", "position", "coordinates", "navigation", "map"],
            "gratitude": ["welcome", "pleasure", "assist", "help", "support"],
            "combat": ["enemy", "hostile", "titan", "weapon", "combat", "attack"],
            "mission": ["mission", "objective", "protocol", "orders", "task"],
            "status": ["status", "condition", "systems", "operational", "functional"]
        }
        
        keywords = context_keywords.get(topic, [])
        
        for phrase, path in self.bt_clips.items():
            if any(keyword in phrase for keyword in keywords):
                context_phrases.append(phrase)
        
        return context_phrases

    def detect_emotional_tone(self, text: str) -> str:
        """Detect the emotional tone of a text."""
        text_lower = text.lower()
        
        tone_indicators = {
            "urgent": ["danger", "warning", "alert", "emergency", "critical", "hurry", "quick"],
            "cautious": ["careful", "caution", "beware", "watch out", "attention"],
            "positive": ["good", "great", "excellent", "perfect", "wonderful", "amazing"],
            "concerned": ["worry", "concern", "afraid", "scared", "nervous", "anxious"],
            "determined": ["must", "will", "shall", "determined", "committed", "resolve"],
            "neutral": ["understood", "acknowledged", "copy that", "roger", "affirmative"]
        }
        
        tone_scores = {}
        for tone, indicators in tone_indicators.items():
            score = sum(1 for indicator in indicators if indicator in text_lower)
            if score > 0:
                tone_scores[tone] = score
        
        if tone_scores:
            return max(tone_scores, key=tone_scores.get)
        return "neutral"

    def get_emotion_matching_phrases(self, text: str) -> list:
        """Get phrases that match the emotional tone of the text."""
        tone = self.detect_emotional_tone(text)
        
        emotion_keywords = {
            "urgent": ["danger", "warning", "alert", "emergency", "critical", "hurry"],
            "cautious": ["careful", "caution", "beware", "watch out", "attention"],
            "positive": ["good", "great", "excellent", "perfect", "wonderful", "congratulations"],
            "concerned": ["worry", "concern", "careful", "safe", "protect"],
            "determined": ["must", "will", "shall", "determined", "committed", "resolve", "protocol"],
            "neutral": ["understood", "acknowledged", "copy that", "roger", "affirmative", "standing by"]
        }
        
        keywords = emotion_keywords.get(tone, [])
        
        matching_phrases = []
        for phrase, path in self.bt_clips.items():
            if any(keyword in phrase for keyword in keywords):
                matching_phrases.append(phrase)
        
        return matching_phrases

    def try_enhanced_matching(self, response_text: str) -> str:
        """Try to find a matching clip using all enhanced methods."""
        if not response_text:
            return None
            
        normalized = normalize_phrase(response_text)
        
        # 1. Exact match
        if normalized in self.bt_clips:
            return self.bt_clips[normalized]
        
        # 2. Semantic similarity
        if self.semantic_vectorizer and self.semantic_clip_matrix is not None:
            try:
                response_vector = self.semantic_vectorizer.transform([normalized])
                similarities = cosine_similarity(response_vector, self.semantic_clip_matrix)
                best_match_idx = np.argmax(similarities)
                best_similarity = similarities[0][best_match_idx]
                
                if best_similarity > 0.3:
                    best_phrase = self.semantic_clip_phrases[best_match_idx]
                    path = self.bt_clips.get(best_phrase)
                    if path:
                        return path
            except Exception as e:
                print(f"    ⚠ Semantic matching failed: {e}")
        
        # 3. Context-aware
        context_phrases = self.get_context_aware_phrases()
        if context_phrases:
            for phrase in context_phrases:
                if normalized in phrase or phrase in normalized:
                    return self.bt_clips.get(phrase)
        
        # 4. Emotional tone
        emotion_phrases = self.get_emotion_matching_phrases(response_text)
        if emotion_phrases:
            for phrase in emotion_phrases:
                if normalized in phrase or phrase in normalized:
                    return self.bt_clips.get(phrase)
        
        return None

def test_semantic_similarity(tester):
    """Test semantic similarity matching."""
    print("\n" + "="*60)
    print("TEST 1: Semantic Similarity Matching")
    print("="*60)
    
    if not tester.initialize_semantic_matching():
        print("⚠ Skipping semantic similarity tests")
        return False
    
    test_phrases = [
        "be careful pilot",
        "thank you for your help",
        "i understand completely",
        "please wait a moment",
        "good job pilot"
    ]
    
    for phrase in test_phrases:
        print(f"\n  Testing: '{phrase}'")
        normalized = normalize_phrase(phrase)
        
        response_vector = tester.semantic_vectorizer.transform([normalized])
        similarities = cosine_similarity(response_vector, tester.semantic_clip_matrix)
        best_match_idx = np.argmax(similarities)
        best_similarity = similarities[0][best_match_idx]
        best_phrase = tester.semantic_clip_phrases[best_match_idx]
        
        print(f"    Best match: '{best_phrase}' (similarity: {best_similarity:.2f})")
        
        if best_similarity > 0.3:
            print(f"    ✓ Match found above threshold")
        else:
            print(f"    ⚠ Match below threshold")
    
    return True

def test_context_aware_selection(tester):
    """Test context-aware phrase selection."""
    print("\n" + "="*60)
    print("TEST 2: Context-Aware Phrase Selection")
    print("="*60)
    
    contexts = [
        {"topic": "weather", "user_emotion": "neutral"},
        {"topic": "location", "user_emotion": "seeking_help"},
        {"topic": "gratitude", "user_emotion": "positive"},
        {"topic": "combat", "user_emotion": "concerned"},
        {"topic": "mission", "user_emotion": "determined"}
    ]
    
    for context in contexts:
        tester.current_context = context
        print(f"\n  Context: {context}")
        
        phrases = tester.get_context_aware_phrases()
        print(f"    Found {len(phrases)} context-aware phrases")
        
        if phrases:
            print(f"    Sample phrases:")
            for phrase in phrases[:3]:
                print(f"      - '{phrase}'")
        else:
            print(f"    ⚠ No context-aware phrases found")
    
    return True

def test_emotional_tone_matching(tester):
    """Test emotional tone matching."""
    print("\n" + "="*60)
    print("TEST 3: Emotional Tone Matching")
    print("="*60)
    
    test_phrases = [
        ("Be careful, there is danger ahead", "cautious"),
        ("Great job, pilot! You did excellent work", "positive"),
        ("Warning! Enemy titans inbound!", "urgent"),
        ("I am worried about the mission status", "concerned"),
        ("We must complete the objective immediately", "determined"),
        ("Understood, copy that", "neutral")
    ]
    
    for phrase, expected_tone in test_phrases:
        print(f"\n  Testing: '{phrase}'")
        detected_tone = tester.detect_emotional_tone(phrase)
        print(f"    Expected tone: {expected_tone}")
        print(f"    Detected tone: {detected_tone}")
        
        if detected_tone == expected_tone:
            print(f"    ✓ Tone matched correctly")
        else:
            print(f"    ⚠ Tone mismatch")
        
        emotion_phrases = tester.get_emotion_matching_phrases(phrase)
        print(f"    Found {len(emotion_phrases)} emotion-matching phrases")
        
        if emotion_phrases:
            print(f"    Sample phrases:")
            for p in emotion_phrases[:3]:
                print(f"      - '{p}'")

def test_enhanced_matching_integration(tester):
    """Test the complete enhanced matching pipeline."""
    print("\n" + "="*60)
    print("TEST 4: Enhanced Matching Integration")
    print("="*60)
    
    tester.initialize_semantic_matching()
    tester.current_context = {"topic": "weather", "user_emotion": "neutral"}
    
    test_responses = [
        "You're welcome, Pilot.",
        "Be careful, pilot.",
        "Copy that, Pilot. Stand by.",
        "Understood, but I do recommend you move",
        "Standing by, pilot. Climb onto my hand."
    ]
    
    for response in test_responses:
        print(f"\n  Testing response: '{response}'")
        
        result = tester.try_enhanced_matching(response)
        
        if result:
            print(f"    ✓ Match found: {result}")
        else:
            print(f"    ⚠ No match found")

def main():
    print("BT-7274 Enhanced Matching Test Suite")
    print("="*60)
    
    try:
        tester = EnhancedMatchingTester()
        
        if not tester.bt_clips:
            print("\n⚠ No BT clips loaded. Please check the BT-7274.Voicepack directory.")
            return 1
        
        test_semantic_similarity(tester)
        test_context_aware_selection(tester)
        test_emotional_tone_matching(tester)
        test_enhanced_matching_integration(tester)
        
        print("\n" + "="*60)
        print("All tests completed!")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())