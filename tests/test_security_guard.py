# tests/test_security_guard.py
import pytest
from bt7274_workstation.security_guard import SecurityGuard, DataClassifier, Sanitizer


class TestDataClassifier:
    def test_classifies_email_as_pii(self):
        classifier = DataClassifier()
        result = classifier.contains_pii("my email is pilot@frontier.mil")
        assert result is True

    def test_classifies_ip_address_as_pii(self):
        classifier = DataClassifier()
        result = classifier.contains_pii("server at 192.168.1.1 is down")
        assert result is True

    def test_classifies_coordinates_as_pii(self):
        classifier = DataClassifier()
        result = classifier.contains_pii("coordinates are 50.9311, 5.3378")
        assert result is True

    def test_classifies_phone_as_pii(self):
        classifier = DataClassifier()
        result = classifier.contains_pii("call me at 555-123-4567")
        assert result is True

    def test_clean_text_has_no_pii(self):
        classifier = DataClassifier()
        result = classifier.contains_pii("what is the weather today")
        assert result is False

    def test_classifies_credit_card_as_pii(self):
        classifier = DataClassifier()
        result = classifier.contains_pii("card number 4111-1111-1111-1111")
        assert result is True


class TestSanitizer:
    def test_redacts_email(self):
        sanitizer = Sanitizer()
        result = sanitizer.redact("contact pilot@frontier.mil for help")
        assert "pilot@frontier.mil" not in result
        assert "[REDACTED" in result

    def test_redacts_ip_address(self):
        sanitizer = Sanitizer()
        result = sanitizer.redact("connect to 10.0.0.1 please")
        assert "10.0.0.1" not in result
        assert "[REDACTED" in result

    def test_redacts_coordinates(self):
        sanitizer = Sanitizer()
        result = sanitizer.redact("go to 50.9311, 5.3378 now")
        assert "50.9311" not in result
        assert "[REDACTED" in result

    def test_redacts_phone_number(self):
        sanitizer = Sanitizer()
        result = sanitizer.redact("text 555-123-4567 later")
        assert "555-123-4567" not in result
        assert "[REDACTED" in result

    def test_preserves_clean_text(self):
        sanitizer = Sanitizer()
        result = sanitizer.redact("what is the mission status")
        assert result == "what is the mission status"

    def test_redacts_credit_card(self):
        sanitizer = Sanitizer()
        result = sanitizer.redact("use 4111-1111-1111-1111 for payment")
        assert "4111-1111-1111-1111" not in result
        assert "[REDACTED" in result

    def test_sanitize_llm_prompt_strips_location_when_not_asked(self):
        sanitizer = Sanitizer()
        prompt = "Pilot is in Hasselt, Belgium. What is the weather?"
        result = sanitizer.sanitize_llm_prompt(prompt, purpose="general")
        assert "Hasselt" not in result

    def test_sanitize_llm_prompt_keeps_location_when_weather_purpose(self):
        sanitizer = Sanitizer()
        prompt = "Pilot is in Hasselt, Belgium. What is the weather?"
        result = sanitizer.sanitize_llm_prompt(prompt, purpose="weather")
        assert "Hasselt" in result

    def test_sanitize_llm_prompt_keeps_location_when_navigation_purpose(self):
        sanitizer = Sanitizer()
        prompt = "Pilot is in Hasselt, Belgium. How do I get to Brussels?"
        result = sanitizer.sanitize_llm_prompt(prompt, purpose="navigation")
        assert "Hasselt" in result


class TestSecurityGuard:
    def test_validate_url_allows_https(self):
        guard = SecurityGuard()
        result = guard.validate_url("https://api.open-meteo.com/v1/forecast")
        assert result is True

    def test_validate_url_blocks_http_by_default(self):
        guard = SecurityGuard()
        result = guard.validate_url("http://evil.com/steal")
        assert result is False

    def test_validate_url_allows_http_if_allowlisted(self):
        guard = SecurityGuard(allow_http_hosts=["ip-api.com"])
        result = guard.validate_url("http://ip-api.com/json/")
        assert result is True

    def test_validate_url_blocks_non_allowlisted_http(self):
        guard = SecurityGuard(allow_http_hosts=["ip-api.com"])
        result = guard.validate_url("http://evil.com/steal")
        assert result is False

    def test_validate_url_allows_localhost(self):
        guard = SecurityGuard()
        result = guard.validate_url("http://localhost:11434/api/chat")
        assert result is True  # localhost is always allowed

    def test_rate_limit_allows_first_request(self):
        guard = SecurityGuard()
        assert guard.check_rate_limit("open-meteo") is True

    def test_rate_limit_blocks_too_many_requests(self):
        guard = SecurityGuard(max_calls_per_minute={"open-meteo": 2})
        assert guard.check_rate_limit("open-meteo") is True
        assert guard.check_rate_limit("open-meteo") is True
        assert guard.check_rate_limit("open-meteo") is False

    def test_audit_log_records_event(self, tmp_path):
        guard = SecurityGuard(audit_log_dir=str(tmp_path))
        guard.audit("outbound_request", {
            "destination": "api.open-meteo.com",
            "data_type": "weather_query",
            "sanitized": True,
        })
        log_files = list(tmp_path.glob("*.jsonl"))
        assert len(log_files) == 1
