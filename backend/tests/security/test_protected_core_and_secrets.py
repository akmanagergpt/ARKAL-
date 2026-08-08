"""Protected Core boundary and Secret Vault boundary.

Covers ARK-REQ-0071, 0098-0103, 0110-0112, 0236.

The secret controls are deliberately structural. Most assert that a capability
does not exist rather than that a rule rejects it: the boundary is a type with
nowhere to put a raw value, not a policy that raw values should be handled
carefully.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml
from arkali.control.policy.protected_core import (
    REQUIRED_GATE,
    MutationAttempt,
    ProtectedCoreBoundary,
)
from arkali.control.policy.secret_reference import (
    PermissionBroker,
    SecretReference,
    assert_no_raw_secret,
)
from arkali.kernel.contracts.results import HonestState
from arkali.control.policy.policy_errors import (
    HumanGateNotRecorded,
    ProtectedCoreMutation,
    RawSecretLeak,
    SecretAccessDenied,
)

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def boundary() -> ProtectedCoreBoundary:
    return ProtectedCoreBoundary.load(REPO)


@pytest.fixture(scope="module")
def declared_protected() -> set[str]:
    raw = yaml.safe_load(
        (REPO / "docs/canonical/AUTHORITY_MAP.yaml").read_text(encoding="utf-8")
    )
    return {n for n, m in raw["contexts"].items() if m.get("protected_core")}


class TestProtectedCoreMembershipIsAuthoritative:
    def test_membership_matches_the_authority_map_exactly(
        self, boundary: ProtectedCoreBoundary, declared_protected: set[str]
    ) -> None:
        """ARK-REQ-0112: no duplicate list, no local reinterpretation."""
        assert set(boundary.contexts) == declared_protected

    def test_the_seven_canonical_members_are_present(
        self, boundary: ProtectedCoreBoundary
    ) -> None:
        """SECURITY_ARCHITECTURE.md §5."""
        for name in (
            "control.policy",
            "control.isolation",
            "control.architecture",
            "evidence.audit",
            "acceptance.engine",
            "lifecycle.release",
            "lifecycle.recovery",
        ):
            assert name in boundary.contexts

    def test_acceptance_contracts_are_protected(
        self, boundary: ProtectedCoreBoundary
    ) -> None:
        """ARK-REQ-0071, 0236: independence is structural."""
        assert boundary.is_protected("backend/arkali/acceptance/checker.py")
        assert boundary.is_protected(
            "backend/arkali/control/architecture/gates/base.py"
        )

    def test_an_ordinary_path_is_not_protected(
        self, boundary: ProtectedCoreBoundary
    ) -> None:
        """Proves the boundary discriminates rather than refusing everything."""
        assert not boundary.is_protected("backend/arkali/engineering/agent/x.py")
        assert not boundary.is_protected("docs/build/BUILD_STATE.md")

    def test_there_is_no_api_to_change_membership(self) -> None:
        """ARK-REQ-0112 enforced by omission."""
        public = {n for n in dir(ProtectedCoreBoundary) if not n.startswith("_")}
        for forbidden in ("add", "remove", "set_members", "extend", "update"):
            assert forbidden not in public


class TestProtectedCoreDirectMutationIsRefused:
    @pytest.mark.parametrize(
        "actor",
        ["engineering.agent", "implementing_actor", "execution.workflow",
         "engineering.plugin", "acceptance.engine"],
    )
    def test_direct_mutation_is_refused_for_every_actor(
        self, boundary: ProtectedCoreBoundary, actor: str
    ) -> None:
        with pytest.raises(ProtectedCoreMutation):
            boundary.authorize(
                MutationAttempt(
                    path="backend/arkali/control/policy/pdp.py", actor=actor
                )
            )

    def test_the_lifecycle_route_still_requires_the_gate(
        self, boundary: ProtectedCoreBoundary
    ) -> None:
        """ARK-REQ-0110: claiming the lifecycle is not the same as passing GATE 2."""
        with pytest.raises(HumanGateNotRecorded):
            boundary.authorize(
                MutationAttempt(
                    path="backend/arkali/control/policy/pdp.py",
                    actor="lifecycle.release",
                    via_stable_core_lifecycle=True,
                )
            )

    def test_a_wrong_gate_does_not_satisfy_the_requirement(
        self, boundary: ProtectedCoreBoundary
    ) -> None:
        with pytest.raises(HumanGateNotRecorded):
            boundary.authorize(
                MutationAttempt(
                    path="backend/arkali/control/policy/pdp.py",
                    actor="lifecycle.release",
                    via_stable_core_lifecycle=True,
                    recorded_human_gates=("HUMAN_GATE_4", "HUMAN_GATE_1"),
                )
            )

    def test_the_full_canonical_route_is_accepted(
        self, boundary: ProtectedCoreBoundary
    ) -> None:
        """Proves the refusals above are specific, not blanket."""
        owner = boundary.authorize(
            MutationAttempt(
                path="backend/arkali/control/policy/pdp.py",
                actor="lifecycle.release",
                via_stable_core_lifecycle=True,
                recorded_human_gates=(REQUIRED_GATE,),
            )
        )
        assert owner == "control.policy"

    def test_an_unprotected_path_needs_no_gate(
        self, boundary: ProtectedCoreBoundary
    ) -> None:
        assert boundary.authorize(
            MutationAttempt(path="README.md", actor="engineering.agent")
        ) == ""


class TestSecretBoundaryIsStructural:
    def test_a_reference_has_no_field_that_can_carry_a_value(self) -> None:
        """ARK-REQ-0098, 0101: the type has nowhere to put a raw secret."""
        fields = set(SecretReference.model_fields)
        assert fields == {"handle", "scope", "revoked"}
        for forbidden in ("value", "secret", "token", "password", "material"):
            assert forbidden not in fields

    def test_rendering_a_reference_never_looks_like_a_value(self) -> None:
        rendered = str(SecretReference(handle="h1", scope="provider.anthropic"))
        assert "secret-ref" in rendered
        assert "h1" in rendered

    def test_the_broker_has_no_store_function(self) -> None:
        """ARK-REQ-0099, 0100: no automated actor may write a raw secret."""
        public = {n for n in dir(PermissionBroker) if not n.startswith("_")}
        for forbidden in ("store", "write", "provision", "set", "put", "export"):
            assert forbidden not in public

    def test_resolving_a_reference_to_a_raw_value_is_refused(self) -> None:
        broker = PermissionBroker(HonestState.PASS, "DPAPI")
        reference = broker.issue(
            "h1", "provider.anthropic", authorized_scopes=("provider.anthropic",)
        )
        with pytest.raises(RawSecretLeak):
            broker.resolve(reference)


class TestSecretScopeAndKeyProtection:
    def test_issuing_outside_a_preauthorized_scope_is_refused(self) -> None:
        broker = PermissionBroker(HonestState.PASS, "DPAPI")
        with pytest.raises(SecretAccessDenied):
            broker.issue("h1", "provider.openai", authorized_scopes=("provider.anthropic",))

    def test_issuing_inside_scope_succeeds(self) -> None:
        broker = PermissionBroker(HonestState.PASS, "DPAPI")
        reference = broker.issue(
            "h1", "provider.anthropic", authorized_scopes=("provider.anthropic",)
        )
        assert reference.is_usable

    def test_a_revoked_reference_is_unusable(self) -> None:
        broker = PermissionBroker(HonestState.PASS, "DPAPI")
        broker.issue("h1", "s", authorized_scopes=("s",))
        assert not broker.revoke("h1").is_usable

    @pytest.mark.parametrize(
        "state",
        [
            HonestState.NOT_CONFIGURED,
            HonestState.UNSUPPORTED,
            HonestState.NOT_TESTED,
            HonestState.EXTERNAL_UNAVAILABLE,
        ],
    )
    def test_without_os_key_protection_capabilities_are_unsupported(
        self, state: HonestState
    ) -> None:
        """ARK-REQ-0102, 0103: never stored unprotected, never degraded."""
        broker = PermissionBroker(state)
        assert broker.capability_state is HonestState.UNSUPPORTED
        with pytest.raises(SecretAccessDenied):
            broker.issue("h1", "s", authorized_scopes=("s",))


def synthetic_secret(kind: str) -> str:
    """Build a secret-shaped fixture without writing one as a literal.

    The repository's own secret scanner (`check_repository_structure.py` check 9)
    correctly flags secret-shaped literals in tracked files. A test proving the
    leak guard works needs input that looks like a secret, so the shapes are
    assembled at run time: the guard sees a complete value, the scanner sees no
    literal, and neither check is weakened to accommodate the other.
    """
    shapes = {
        "pem": "-----BEGIN RSA " + "PRIVATE KEY" + "-----",
        "openai": "sk-" + "abcdefghijklmnopqrstuvwxyz123456",
        "github": "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890",
        "aws": "AKIA" + "IOSFODNN7EXAMPLE",
    }
    return shapes[kind]


class TestNoRawSecretReachesAForbiddenSink:
    @pytest.mark.parametrize("kind", ["pem", "openai", "github", "aws"])
    @pytest.mark.parametrize(
        "sink", ["evidence artifact", "log", "prompt", "source export", "release artifact"]
    )
    def test_raw_material_is_refused_at_every_forbidden_sink(
        self, kind: str, sink: str
    ) -> None:
        """ARK-REQ-0098."""
        with pytest.raises(RawSecretLeak):
            assert_no_raw_secret(f"context {synthetic_secret(kind)} more", sink=sink)

    def test_a_reference_passes_the_same_sinks(self) -> None:
        """Proves the guard discriminates rather than rejecting everything."""
        reference = SecretReference(handle="h1", scope="provider.anthropic")
        for sink in ("evidence artifact", "log", "prompt"):
            assert_no_raw_secret(str(reference), sink=sink)

    def test_the_guard_names_the_sink_that_refused(self) -> None:
        with pytest.raises(RawSecretLeak) as caught:
            assert_no_raw_secret(synthetic_secret("openai"), sink="log")
        assert "log" in str(caught.value)
