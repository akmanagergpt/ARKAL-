"""C-11 provider/model record behaviour and refusals (Phase 9 Package 1).

NOTHING IS TRANSCRIBED. The seven owned concerns, the five reference-only
consumers and the provider-health state vocabulary are read from
`AUTHORITY_MAP.yaml` and from the canonical `ProviderHealth` machine inside the
tests, so a canonical change moves these controls with it instead of leaving
them asserting a stale list (the F-0032 pattern).

NO PROVIDER IS CONTACTED. ARK-REQ-0219 forbids fabricating or simulating an
external-provider result, so nothing here stands in for one. Every case is about
what a record may declare, not about what a provider replied.
"""

from __future__ import annotations

import pathlib

import pytest

from arkali.control.registry.provider.errors import (
    InvalidProviderIdentity,
    RawSecretInProviderConfiguration,
    UnknownProviderHealthState,
)
from arkali.control.registry.provider.provider_authority import ProviderAuthority
from arkali.control.registry.provider.provider_health_state_machine import (
    DEFINITION,
    build,
)
from arkali.control.registry.provider.provider_record import ProviderRecord
from pydantic import ValidationError

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def authority() -> ProviderAuthority:
    return ProviderAuthority.load(REPO)


def record(**overrides: object) -> ProviderRecord:
    fields: dict[str, object] = {"identity": "anthropic"}
    fields.update(overrides)
    return ProviderRecord(**fields)  # type: ignore[arg-type]


class TestTheAuthorityIsParsedNotDeclared:
    """ARK-REQ-0052's scope is governed data, not a list in this context."""

    def test_the_registry_is_the_declared_owner(
        self, authority: ProviderAuthority
    ) -> None:
        assert authority.owner == "control.registry.provider"

    def test_the_owned_concerns_are_the_canonical_seven(
        self, authority: ProviderAuthority
    ) -> None:
        concerns = authority.owned_concerns()
        assert len(concerns) == 7, f"provider_authority changed: {concerns}"
        assert len(set(concerns)) == len(concerns)

    def test_copying_and_caching_are_forbidden(
        self, authority: ProviderAuthority
    ) -> None:
        """ARK-REQ-0053, read from the map rather than assumed."""
        assert authority.copying_permitted is False
        assert authority.caching_permitted is False

    def test_every_reference_only_consumer_is_a_real_context(
        self, authority: ProviderAuthority
    ) -> None:
        consumers = authority.reference_only_consumers()
        assert consumers, "no consumer declared; ARK-REQ-0053 would be vacuous"
        assert authority.owner not in consumers, (
            "the owner cannot be a reference-only consumer of itself"
        )

    def test_the_owner_owns_each_declared_concern(
        self, authority: ProviderAuthority
    ) -> None:
        for concern in authority.owned_concerns():
            assert authority.owns(concern)
        assert not authority.owns("provider_runtime")


class TestTheRecordCarriesExactlyTheOwnedConcerns:
    """The model and the map must agree in both directions."""

    def test_the_model_fields_are_the_owned_concerns(
        self, authority: ProviderAuthority
    ) -> None:
        assert set(ProviderRecord.model_fields) == set(authority.owned_concerns())

    def test_an_eighth_concern_is_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ProviderRecord(  # type: ignore[call-arg]
                identity="anthropic", provider_runtime="live"
            )

    def test_a_record_is_frozen(self) -> None:
        subject = record()
        with pytest.raises(ValidationError):
            subject.identity = "other"  # type: ignore[misc]


class TestHealthIsTheCanonicalMachines:
    """No second provider-health authority may appear here."""

    def test_every_canonical_state_is_accepted(self) -> None:
        for state in DEFINITION.states:
            record(health=state).validate_record()

    def test_a_state_the_machine_does_not_declare_is_refused(self) -> None:
        with pytest.raises(UnknownProviderHealthState):
            record(health="EXCELLENT").validate_record()

    def test_the_default_health_is_the_machines_initial_state(self) -> None:
        assert record().health == DEFINITION.states[0]

    def test_the_machine_authority_is_this_context(self) -> None:
        assert DEFINITION.authority == "control.registry.provider"
        assert build().machine == DEFINITION.machine

    def test_the_record_declares_no_transition_of_its_own(self) -> None:
        """Transitions belong to the machine; the record only holds a state."""
        public = [n for n in dir(ProviderRecord) if not n.startswith("_")]
        for name in public:
            assert "transition" not in name.lower()


class TestIdentityRefusals:
    """Each refusal asserts its own type, so none passes for another reason."""

    @pytest.mark.parametrize("identity", ["", "Anthropic", "1provider", "has space"])
    def test_a_malformed_provider_identity_is_refused(self, identity: str) -> None:
        with pytest.raises(InvalidProviderIdentity):
            record(identity=identity).validate_record()

    def test_a_malformed_model_identity_is_refused(self) -> None:
        with pytest.raises(InvalidProviderIdentity):
            record(model_identity=("Claude Sonnet",)).validate_record()

    def test_a_malformed_fallback_identity_is_refused(self) -> None:
        with pytest.raises(InvalidProviderIdentity):
            record(fallback=("Not A Provider",)).validate_record()

    def test_a_provider_may_not_fall_back_to_itself(self) -> None:
        with pytest.raises(InvalidProviderIdentity):
            record(identity="anthropic", fallback=("anthropic",)).validate_record()

    def test_a_well_formed_record_is_accepted(self) -> None:
        record(
            identity="anthropic",
            model_identity=("claude.sonnet", "claude.opus"),
            fallback=("openai",),
            health="HEALTHY",
        ).validate_record()


class TestConfigurationCannotCarryASecret:
    """C-09's boundary, applied where an API key would actually be smuggled in."""

    def test_configuration_holds_opaque_handles(self) -> None:
        subject = record(configuration=("anthropic-key", "anthropic.backup"))
        subject.validate_record()
        assert subject.configuration == ("anthropic-key", "anthropic.backup")

    @pytest.mark.parametrize(
        "leak",
        [
            "sk-" + "abcdefghijklmnopqrstuvwxyz",
            "ghp_" + "abcdefghijklmnopqrstuvwxyz12",
            "AKIA" + "IOSFODNN7EXAMPLE",
            "-----BEGIN RSA " + "PRIVATE KEY" + "-----",
            "",
        ],
    )
    def test_a_value_cannot_masquerade_as_a_handle(self, leak: str) -> None:
        with pytest.raises(RawSecretInProviderConfiguration):
            record(configuration=(leak,)).validate_record()

    def test_the_record_holds_no_policy_state(self) -> None:
        """`revoked` belongs to the Permission Broker; mirroring it here would be
        the ARK-REQ-0053 disease pointed at a different authority."""
        subject = record(configuration=("anthropic-key",))
        assert not hasattr(subject, "usable_configuration")
        for field in ProviderRecord.model_fields:
            assert "revok" not in field

    @pytest.mark.parametrize(
        "leak",
        [
            "sk-" + "abcdefghijklmnopqrstuvwxyz",
            "ghp_" + "abcdefghijklmnopqrstuvwxyz12",
            "AKIA" + "IOSFODNN7EXAMPLE",
            "-----BEGIN RSA " + "PRIVATE KEY" + "-----",
        ],
    )
    def test_free_form_metadata_carrying_a_raw_secret_is_refused(
        self, leak: str
    ) -> None:
        with pytest.raises(RawSecretInProviderConfiguration):
            record(availability=leak).validate_record()
        with pytest.raises(RawSecretInProviderConfiguration):
            record(cost_metadata=leak).validate_record()

    def test_ordinary_metadata_is_accepted(self) -> None:
        record(availability="regional", cost_metadata="per-1k-tokens").validate_record()


class TestNoProviderIsContacted:
    """Package 1 declares. It runs nothing and simulates nothing."""

    def test_the_record_exposes_no_invocation_operation(self) -> None:
        forbidden = (
            "invoke", "call", "complete", "request", "send", "stream",
            "client", "session", "connect", "runtime", "simulate",
        )
        public = [n for n in dir(ProviderRecord) if not n.startswith("_")]
        for name in public:
            assert not any(word in name.lower() for word in forbidden), name

    def test_the_record_holds_no_live_measurement(self) -> None:
        """Health is a declared state, not a probe result this package produced."""
        subject = record(health="HEALTHY")
        assert subject.health in DEFINITION.states
        assert not hasattr(subject, "latency")
        assert not hasattr(subject, "last_response")
