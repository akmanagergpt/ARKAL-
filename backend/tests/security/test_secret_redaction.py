"""`control.policy.secret_reference.redact_raw_secrets` (ARK-REQ-0169/0357,
Phase 25): the same C-09 pattern `assert_no_raw_secret` already enforces,
reused for redaction rather than refusal.
"""

from __future__ import annotations

import pytest
from arkali.control.policy.secret_reference import REDACTED_TOKEN, redact_raw_secrets
from tests.security.test_protected_core_and_secrets import synthetic_secret


class TestRedactRawSecretsReusesTheRealPattern:
    @pytest.mark.parametrize("kind", ["pem", "openai", "github", "aws"])
    def test_every_secret_shape_is_replaced(self, kind: str) -> None:
        secret = synthetic_secret(kind)
        redacted = redact_raw_secrets(f"before {secret} after")
        assert secret not in redacted
        assert REDACTED_TOKEN in redacted
        assert "before" in redacted
        assert "after" in redacted

    def test_ordinary_text_is_returned_unchanged(self) -> None:
        text = "no secrets live in this ordinary sentence at all."
        assert redact_raw_secrets(text) == text

    def test_multiple_secrets_in_one_payload_are_all_redacted(self) -> None:
        payload = f"{synthetic_secret('openai')} and {synthetic_secret('github')}"
        redacted = redact_raw_secrets(payload)
        assert synthetic_secret("openai") not in redacted
        assert synthetic_secret("github") not in redacted
        assert redacted.count(REDACTED_TOKEN) == 2

    def test_a_partial_mask_is_never_produced(self) -> None:
        """The whole match is replaced, never truncated in place - a
        truncated key can still be a working credential."""
        secret = synthetic_secret("aws")
        redacted = redact_raw_secrets(secret)
        assert secret[:8] not in redacted
        assert secret[-8:] not in redacted
