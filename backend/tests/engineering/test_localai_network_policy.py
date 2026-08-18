"""Local-Only proof: loopback local-AI calls stay permitted, external denied."""

from __future__ import annotations

from arkali.engineering.localai.network_policy import (
    LOOPBACK_HOSTS,
    gate_local_call,
    is_loopback_endpoint,
)


class _RecordingPdp:
    """Composition-root double proving `gate_local_call` derives the loopback
    fact itself rather than trusting a caller-supplied claim."""

    def __init__(self, decision: str = "AUTO") -> None:
        self.decision = decision
        self.calls: list[dict[str, object]] = []

    def decide_network_egress(
        self, *, actor: str, trust_tier: str, local_only: bool,
        target_is_loopback: bool | None = None,
    ) -> str:
        self.calls.append({
            "actor": actor, "trust_tier": trust_tier, "local_only": local_only,
            "target_is_loopback": target_is_loopback,
        })
        return self.decision


class TestLoopbackDetection:
    def test_127_0_0_1_is_loopback(self) -> None:
        assert is_loopback_endpoint("http://127.0.0.1:11434") is True

    def test_localhost_is_loopback(self) -> None:
        assert is_loopback_endpoint("http://localhost:11434") is True

    def test_a_lan_host_is_not_loopback(self) -> None:
        assert is_loopback_endpoint("http://192.168.1.5:11434") is False

    def test_a_public_host_is_not_loopback(self) -> None:
        assert is_loopback_endpoint("https://api.example.com") is False

    def test_every_declared_loopback_host_round_trips(self) -> None:
        for host in LOOPBACK_HOSTS:
            netloc = f"[{host}]" if ":" in host else host
            assert is_loopback_endpoint(f"http://{netloc}:1234") is True


class TestGateDerivesTheFactItselfAndAsksTheRealPdp:
    def test_a_loopback_endpoint_is_classified_as_loopback_to_the_pdp(self) -> None:
        pdp = _RecordingPdp()
        gate_local_call(
            pdp, endpoint="http://127.0.0.1:11434", actor="localai",
            trust_tier="TRUST-1", local_only=True,
        )
        assert pdp.calls[0]["target_is_loopback"] is True

    def test_a_non_loopback_endpoint_is_classified_as_external_to_the_pdp(self) -> None:
        pdp = _RecordingPdp()
        gate_local_call(
            pdp, endpoint="http://203.0.113.9:11434", actor="localai",
            trust_tier="TRUST-1", local_only=False,
        )
        assert pdp.calls[0]["target_is_loopback"] is False

    def test_the_pdps_decision_is_returned_unmodified(self) -> None:
        pdp = _RecordingPdp(decision="DENY")
        result = gate_local_call(
            pdp, endpoint="http://127.0.0.1:11434", actor="localai",
            trust_tier="TRUST-1", local_only=True,
        )
        assert result == "DENY"

    def test_local_only_and_trust_tier_pass_through_unmodified(self) -> None:
        pdp = _RecordingPdp()
        gate_local_call(
            pdp, endpoint="http://127.0.0.1:11434", actor="localai",
            trust_tier="TRUST-2", local_only=True,
        )
        assert pdp.calls[0]["trust_tier"] == "TRUST-2"
        assert pdp.calls[0]["local_only"] is True
