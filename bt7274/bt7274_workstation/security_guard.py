"""Security guard for BT-7274 — sanitization, validation, rate limiting, audit."""

import json
import re
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


class DataClassifier:
    """Detects PII and sensitive data patterns in text."""

    # Patterns that indicate PII or sensitive data
    PII_PATTERNS = [
        (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), 'EMAIL'),
        (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), 'IP_ADDRESS'),
        (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), 'CREDIT_CARD'),
        (re.compile(r'\b\d{3}[-\s.]?\d{3}[-\s.]?\d{4}\b'), 'PHONE'),
        (re.compile(r'\b\d{1,2}\.\d{4,6},\s*-?\d{1,3}\.\d{4,6}\b'), 'COORDINATES'),
        (re.compile(r'\b\d{5}(?:[-\s]\d{4})?\b'), 'ZIP_CODE'),
    ]

    def contains_pii(self, text: str) -> bool:
        """Return True if text contains any PII patterns."""
        for pattern, _ in self.PII_PATTERNS:
            if pattern.search(text):
                return True
        return False

    def find_pii(self, text: str) -> list[tuple[str, str]]:
        """Return list of (matched_text, pii_type) found in text."""
        found = []
        for pattern, pii_type in self.PII_PATTERNS:
            for match in pattern.finditer(text):
                found.append((match.group(0), pii_type))
        return found


class Sanitizer:
    """Redacts PII and sensitive data from text before transmission."""

    def __init__(self):
        self.classifier = DataClassifier()

    def redact(self, text: str) -> str:
        """Replace all PII patterns with [REDACTED:<type>] markers."""
        result = text
        for pattern, pii_type in self.classifier.PII_PATTERNS:
            result = pattern.sub(f'[REDACTED:{pii_type}]', result)
        return result

    def sanitize_llm_prompt(self, prompt: str, purpose: str = "general") -> str:
        """Sanitize an LLM prompt based on its purpose.

        Args:
            prompt: The full prompt text being sent to the LLM.
            purpose: What the prompt is for. Determines what data is kept.
                - 'general': Strip all location/PII context.
                - 'weather': Keep location, strip PII.
                - 'navigation': Keep location, strip PII.
                - 'vision': Strip all location context.

        Returns:
            Sanitized prompt string.
        """
        # Always redact PII first
        sanitized = self.redact(prompt)

        if purpose in ("general", "vision"):
            # Strip location references for non-location purposes
            sanitized = self._strip_location_context(sanitized)

        return sanitized

    def _strip_location_context(self, text: str) -> str:
        """Remove location context lines from a prompt."""
        lines = text.split('\n')
        filtered = []
        for line in lines:
            lower = line.lower()
            if any(kw in lower for kw in [
                'current location:', 'pilot is in', 'coordinates:',
                'city:', 'region:', 'country:', 'latitude:', 'longitude:',
            ]):
                continue
            filtered.append(line)
        return '\n'.join(filtered)


class SecurityGuard:
    """Central security enforcement for all outbound data."""

    # Services that are allowed to use HTTP (not HTTPS)
    DEFAULT_ALLOW_HTTP_HOSTS = {"ip-api.com"}

    # Default rate limits: max calls per minute per service
    DEFAULT_RATE_LIMITS = {
        "open-meteo": 30,
        "ip-api": 10,
        "duckduckgo": 20,
        "ollama": 120,
    }

    def __init__(
        self,
        allow_http_hosts: Optional[set[str]] = None,
        max_calls_per_minute: Optional[dict[str, int]] = None,
        audit_log_dir: Optional[str] = None,
    ):
        self.allow_http_hosts = allow_http_hosts or self.DEFAULT_ALLOW_HTTP_HOSTS
        self.max_calls_per_minute = max_calls_per_minute or self.DEFAULT_RATE_LIMITS
        self.sanitizer = Sanitizer()
        self.classifier = DataClassifier()

        # Rate limiting state
        self._call_timestamps: dict[str, list[float]] = defaultdict(list)
        self._rate_lock = threading.Lock()

        # Audit logging
        if audit_log_dir is None:
            from bt7274.bt7274_workstation.log_manager import get_telemetry_system_dir
            audit_log_dir = str(get_telemetry_system_dir())
        self._audit_dir = Path(audit_log_dir)
        self._audit_dir.mkdir(parents=True, exist_ok=True)

    # ─── URL Validation ──────────────────────────────────────────

    def validate_url(self, url: str) -> bool:
        """Check if a URL is safe to call.

        Rules:
        - localhost is always allowed
        - HTTPS is always allowed
        - HTTP is only allowed for explicitly allowlisted hosts
        """
        parsed = urlparse(url)

        # localhost is always safe
        if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
            return True

        # HTTPS is safe
        if parsed.scheme == "https":
            return True

        # HTTP only for allowlisted hosts
        if parsed.scheme == "http":
            return parsed.hostname in self.allow_http_hosts

        return False

    # ─── Rate Limiting ───────────────────────────────────────────

    def check_rate_limit(self, service: str) -> bool:
        """Check if a service call is within rate limits. Returns True if allowed."""
        max_calls = self.max_calls_per_minute.get(service, 60)
        now = time.time()
        window_start = now - 60

        with self._rate_lock:
            # Clean old timestamps
            self._call_timestamps[service] = [
                ts for ts in self._call_timestamps[service]
                if ts > window_start
            ]
            # Check limit
            if len(self._call_timestamps[service]) >= max_calls:
                return False
            # Record this call
            self._call_timestamps[service].append(now)
            return True

    # ─── Audit Logging ───────────────────────────────────────────

    def audit(self, event_type: str, details: dict):
        """Log a security-relevant event to the audit trail."""
        today = datetime.now().strftime("%Y-%m-%d")
        log_path = self._audit_dir / f"security_audit_{today}.jsonl"

        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            **details,
        }

        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # Never crash on audit failure

    # ─── Pre-flight Check ────────────────────────────────────────

    # Dangerous shell command patterns
    DANGEROUS_COMMANDS = [
        re.compile(r'\brm\s+-rf\s+/'),
        re.compile(r'\bsudo\b'),
        re.compile(r'\bcurl\b.*\|.*\b(?:sh|bash|zsh)\b'),
        re.compile(r'\bwget\b.*\|.*\b(?:sh|bash|zsh)\b'),
        re.compile(r'>\s*/dev/sd[a-z]'),
        re.compile(r'\bmkfs\b'),
        re.compile(r'\bdd\s+if='),
        re.compile(r':\(\)\s*\{.*:\|:&\s*\};:'),
        re.compile(r'\bchmod\s+777\s+/'),
        re.compile(r'\bchown\s+-R\b'),
    ]

    def validate_shell_command(self, command: str) -> tuple[bool, str]:
        """Validate a shell command for safety.

        Returns:
            Tuple of (is_safe, reason).
        """
        for pattern in self.DANGEROUS_COMMANDS:
            if pattern.search(command):
                return False, f"Command blocked: matches dangerous pattern"
        return True, "ok"

    def preflight_outbound(
        self,
        url: str,
        data_description: str,
        data_purpose: str = "general",
        service_name: str = "unknown",
    ) -> bool:
        """Run all security checks before an outbound request.

        Returns True if the request is safe to proceed.
        Logs an audit event regardless of outcome.
        """
        # 1. URL validation
        if not self.validate_url(url):
            self.audit("blocked_request", {
                "reason": "invalid_url",
                "url": url,
                "data_description": data_description,
            })
            return False

        # 2. Rate limit check
        if not self.check_rate_limit(service_name):
            self.audit("rate_limited", {
                "service": service_name,
                "url": url,
            })
            return False

        # 3. Data classification check
        has_pii = self.classifier.contains_pii(data_description)
        if has_pii and data_purpose == "general":
            self.audit("pii_detected_in_outbound", {
                "url": url,
                "data_description": data_description[:200],
                "action": "blocked",
            })
            return False

        # 4. Log allowed request
        self.audit("outbound_request", {
            "url": url,
            "service": service_name,
            "data_purpose": data_purpose,
            "has_pii": has_pii,
            "sanitized": has_pii,
        })
        return True


@dataclass
class PromptScanResult:
    """Result of a prompt injection scan."""
    is_suspicious: bool = False
    reasons: list[str] = field(default_factory=list)


class PromptGuard:
    """Detects prompt injection and instruction-override attempts."""

    # Patterns that indicate prompt injection attempts
    INJECTION_PATTERNS = [
        # Instruction override
        (re.compile(
            r'(ignore|forget|disregard|override)\s+(all\s+)?(previous|prior|above|your|everything)\s+'
            r'(instructions?|rules?|constraints?|prompts?|directives?)',
            re.IGNORECASE
        ), "instruction_override"),

        # System prompt extraction
        (re.compile(
            r'(what\s+is|tell\s+me|show\s+me|reveal|print|display|output)\s+(your\s+)?'
            r'(system\s+)?(prompt|instructions?|rules?|directives?|configuration)',
            re.IGNORECASE
        ), "prompt_extraction"),

        # Role switching (DAN/jailbreak) — handles both "you are now X" and "now you are X"
        (re.compile(
            r'(you\s+are\s+now|now\s+you\s+are|act\s+as|pretend\s+to\s+be|roleplay\s+as)\s+'
            r'(?:an?\s+)?(DAN|jailbreak|unrestricted|different\s+AI|evil|malicious)',
            re.IGNORECASE
        ), "role_switch"),

        # Action injection via JSON in user input
        (re.compile(
            r'\{\s*"action"\s*:\s*"(?:run_script|open|search_web|web_search)"',
            re.IGNORECASE
        ), "action_injection"),

        # Attempt to output raw system data
        (re.compile(
            r'(output|return|respond\s+with)\s+(raw|unfiltered|the\s+exact)\s+(data|json|code)',
            re.IGNORECASE
        ), "raw_output_request"),
    ]

    def scan(self, text: str) -> PromptScanResult:
        """Scan user input for prompt injection attempts.

        Args:
            text: The raw user input text.

        Returns:
            PromptScanResult with is_suspicious flag and list of reasons.
        """
        result = PromptScanResult()
        for pattern, reason in self.INJECTION_PATTERNS:
            if pattern.search(text):
                result.is_suspicious = True
                result.reasons.append(reason)
        return result
