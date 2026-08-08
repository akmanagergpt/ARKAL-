"""Trust tiers, isolation properties, backends and real host probes.

Covers ARK-REQ-0017, 0113, 0114, 0118-0123 and the host-probe half of 0103.

Two things are kept strictly apart, because conflating them is the failure this
phase is most exposed to:

  A. the security model - properties, tiers, composition, refusal semantics.
     Verified deterministically here.
  B. host enforcement availability - what this machine can actually provide.
     Probed for real, and reported as whatever it truly is.

A passing test in section A never implies section B. No simulated backend is
allowed to satisfy a tier.
"""

from __future__ import annotations

import pathlib
import platform

import pytest
from arkali.control.isolation.backend_probe import PROBES, probe_all
from arkali.control.isolation.isolation_contract import (
    BackendDescriptor,
    IsolationAuthority,
)
from arkali.kernel.contracts.results import HonestState
from arkali.control.isolation.isolation_errors import TrustTierViolation

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def authority() -> IsolationAuthority:
    return IsolationAuthority.load(REPO)


@pytest.fixture(scope="module")
def probed(authority: IsolationAuthority) -> tuple[BackendDescriptor, ...]:
    return probe_all(authority, REPO)


def synthetic(name: str, provides: tuple[str, ...]) -> BackendDescriptor:
    """An available backend used only to exercise the composition algebra."""
    return BackendDescriptor(
        name=name, provides=provides, availability=HonestState.PASS
    )


class TestCanonicalModel:
    def test_seven_properties_are_declared(self, authority: IsolationAuthority) -> None:
        """ARK-REQ-0113. The count comes from the map."""
        assert len(authority.properties) == 7
        assert len(set(authority.properties)) == 7

    def test_five_tiers_declare_required_property_sets(
        self, authority: IsolationAuthority
    ) -> None:
        """ARK-REQ-0114."""
        assert authority.tiers == (
            "TRUST-0", "TRUST-1", "TRUST-2", "TRUST-3", "TRUST-4"
        )
        for tier in authority.tiers:
            for prop in authority.required_properties(tier):
                assert prop in authority.properties

    def test_tiers_are_monotonically_stricter(
        self, authority: IsolationAuthority
    ) -> None:
        """Each tier requires everything the one below it does."""
        previous: set[str] = set()
        for tier in authority.tiers:
            current = set(authority.required_properties(tier))
            assert previous <= current, f"{tier} drops a property from the tier below"
            previous = current

    def test_silent_downgrade_is_forbidden(
        self, authority: IsolationAuthority
    ) -> None:
        """ARK-REQ-0122."""
        assert authority.silent_downgrade_permitted is False

    def test_unsatisfiable_means_unsupported_and_deny(
        self, authority: IsolationAuthority
    ) -> None:
        """ARK-REQ-0120."""
        assert authority.capability_state_when_unsatisfiable is HonestState.UNSUPPORTED
        assert authority.on_unsatisfiable == "DENY"

    def test_backend_change_requires_gate_4(
        self, authority: IsolationAuthority
    ) -> None:
        assert authority.backend_change_gate == "HUMAN_GATE_4"


class TestComposition:
    def test_a_composition_satisfying_all_properties_is_accepted(
        self, authority: IsolationAuthority
    ) -> None:
        """ARK-REQ-0118, 0119: backends compose; the union must cover the tier."""
        required = authority.required_properties("TRUST-2")
        parts = (
            synthetic("job_object", ("PROCESS_CONTAINMENT", "RESOURCE_LIMITS")),
            synthetic("workspace_acl", ("FS_CONFINEMENT",)),
            synthetic("wfp_egress", ("NET_EGRESS_CONTROL",)),
            synthetic("vault_detach", ("CREDENTIAL_ISOLATION",)),
        )
        found = authority.resolve("TRUST-2", parts)
        assert found.satisfied
        assert set(required) <= {
            p for b in parts for p in b.provides
        }
        assert found.capability_state is HonestState.PASS

    def test_one_missing_property_fails_the_whole_tier(
        self, authority: IsolationAuthority
    ) -> None:
        """ARK-REQ-0119, 0122: no partial success, no nearest match."""
        parts = (
            synthetic("job_object", ("PROCESS_CONTAINMENT", "RESOURCE_LIMITS")),
            synthetic("workspace_acl", ("FS_CONFINEMENT",)),
            synthetic("vault_detach", ("CREDENTIAL_ISOLATION",)),
        )
        found = authority.resolve("TRUST-2", parts)
        assert not found.satisfied
        assert found.missing == ("NET_EGRESS_CONTROL",)
        assert found.capability_state is HonestState.UNSUPPORTED
        assert found.execution_decision == "DENY"

    def test_an_unavailable_backend_contributes_nothing(
        self, authority: IsolationAuthority
    ) -> None:
        """Declaring a property is not providing it."""
        unavailable = BackendDescriptor(
            name="wfp_egress",
            provides=("NET_EGRESS_CONTROL",),
            availability=HonestState.NOT_CONFIGURED,
        )
        found = authority.resolve("TRUST-2", (unavailable,))
        assert "NET_EGRESS_CONTROL" in found.missing

    def test_not_tested_is_not_availability(
        self, authority: IsolationAuthority
    ) -> None:
        untested = BackendDescriptor(
            name="wfp_egress", provides=("NET_EGRESS_CONTROL",)
        )
        assert untested.availability is HonestState.NOT_TESTED
        assert not untested.is_available
        assert "NET_EGRESS_CONTROL" in authority.resolve("TRUST-2", (untested,)).missing

    def test_trust_0_needs_nothing_and_is_always_satisfiable(
        self, authority: IsolationAuthority
    ) -> None:
        assert authority.required_properties("TRUST-0") == ()
        assert authority.resolve("TRUST-0", ()).satisfied

    def test_unknown_tier_is_refused(self, authority: IsolationAuthority) -> None:
        with pytest.raises(TrustTierViolation):
            authority.required_properties("TRUST-9")


class TestForgedCapabilityIsRejected:
    def test_a_backend_cannot_invent_a_property(
        self, authority: IsolationAuthority
    ) -> None:
        forged = synthetic("job_object", ("PROCESS_CONTAINMENT", "TELEPORTATION"))
        with pytest.raises(TrustTierViolation):
            authority.validate_provided(forged)

    def test_a_backend_cannot_claim_more_than_the_map_declares(
        self, authority: IsolationAuthority
    ) -> None:
        """job_object claiming KERNEL_ISOLATION would satisfy TRUST-3 falsely."""
        forged = synthetic(
            "job_object",
            ("PROCESS_CONTAINMENT", "RESOURCE_LIMITS", "KERNEL_ISOLATION"),
        )
        with pytest.raises(TrustTierViolation):
            authority.validate_provided(forged)

    def test_forged_backend_cannot_satisfy_a_tier_through_resolve(
        self, authority: IsolationAuthority
    ) -> None:
        forged = synthetic(
            "workspace_acl",
            tuple(authority.properties),  # claims everything
        )
        with pytest.raises(TrustTierViolation):
            authority.resolve("TRUST-4", (forged,))


class TestRealHostProbes:
    def test_every_declared_backend_is_probed_or_honestly_untested(
        self, authority: IsolationAuthority, probed: tuple[BackendDescriptor, ...]
    ) -> None:
        assert {b.name for b in probed} == set(authority.declared_backends())

    def test_probe_names_reconcile_with_the_authority_map(
        self, authority: IsolationAuthority
    ) -> None:
        """A probe for a backend the map does not declare would be a private list."""
        assert set(PROBES) <= set(authority.declared_backends())

    def test_no_probe_reports_pass_without_a_reason(
        self, probed: tuple[BackendDescriptor, ...]
    ) -> None:
        for backend in probed:
            assert backend.detail, f"{backend.name} reported {backend.availability} "
            "with no evidence"

    def test_probe_states_are_canonical_honest_states(
        self, probed: tuple[BackendDescriptor, ...]
    ) -> None:
        allowed = {
            HonestState.PASS,
            HonestState.NOT_CONFIGURED,
            HonestState.UNSUPPORTED,
            HonestState.EXTERNAL_UNAVAILABLE,
            HonestState.NOT_TESTED,
        }
        for backend in probed:
            assert backend.availability in allowed

    def test_probes_are_deterministic(
        self, authority: IsolationAuthority
    ) -> None:
        first = {b.name: b.availability for b in probe_all(authority, REPO)}
        second = {b.name: b.availability for b in probe_all(authority, REPO)}
        assert first == second

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-first probes")
    def test_kernel_isolation_is_not_claimed_without_a_backend_providing_it(
        self, authority: IsolationAuthority, probed: tuple[BackendDescriptor, ...]
    ) -> None:
        """The honesty check: TRUST-3/4 only pass if something really provides it."""
        providers = [
            b for b in probed
            if "KERNEL_ISOLATION" in b.provides and b.is_available
        ]
        resolution = authority.resolve("TRUST-3", probed)
        if not providers:
            assert not resolution.satisfied
            assert "KERNEL_ISOLATION" in resolution.missing


class TestArkaliRemainsOperational:
    def test_losing_high_tier_backends_does_not_disable_low_tiers(
        self, authority: IsolationAuthority
    ) -> None:
        """ARK-REQ-0121: the factory and TRUST-2 generation continue.

        Fault injection: remove every kernel-isolation backend and confirm the
        tiers that never needed it are unaffected.
        """
        full = (
            synthetic("job_object", ("PROCESS_CONTAINMENT", "RESOURCE_LIMITS")),
            synthetic("workspace_acl", ("FS_CONFINEMENT",)),
            synthetic("wfp_egress", ("NET_EGRESS_CONTROL",)),
            synthetic("vault_detach", ("CREDENTIAL_ISOLATION",)),
        )
        assert authority.resolve("TRUST-2", full).satisfied
        assert authority.resolve("TRUST-1", full).satisfied
        assert authority.resolve("TRUST-0", full).satisfied
        degraded = authority.resolve("TRUST-3", full)
        assert not degraded.satisfied
        assert degraded.missing == ("KERNEL_ISOLATION",)

    def test_losing_every_backend_leaves_trust_0_working(
        self, authority: IsolationAuthority
    ) -> None:
        assert authority.resolve("TRUST-0", ()).satisfied
        for tier in ("TRUST-1", "TRUST-2", "TRUST-3", "TRUST-4"):
            assert not authority.resolve(tier, ()).satisfied
