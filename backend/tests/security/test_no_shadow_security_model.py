"""Drift controls: the security model has no private copies (ARK-REQ-0241).

Each control mutates a temporary copy of the authority map or the security
document and proves the verdict follows the *authority*, not the validator.
No accepted repository state is modified — the final control asserts that.

This is the F-0013 rule applied to security: a checker must never hold a private
copy of the thing it checks. A shadow security model is worse than a shadow
registry, because the thing being duplicated is what decides whether an action
is allowed.
"""

from __future__ import annotations

import copy
import pathlib

import pytest
import yaml
from arkali.control.isolation.isolation_contract import IsolationAuthority
from arkali.control.policy.operation_class import Decision, OperationClassVocabulary
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.control.policy.protected_core import ProtectedCoreBoundary
from arkali.control.policy.security_matrix import SecurityMatrix
from arkali.kernel.contracts.errors import AuthoritativeSourceError

REPO = pathlib.Path(__file__).resolve().parents[3]
MAP_RELPATH = "docs/canonical/AUTHORITY_MAP.yaml"
SEC_RELPATH = "docs/canonical/SECURITY_ARCHITECTURE.md"

WATCHED = (MAP_RELPATH, SEC_RELPATH)


def mutated_repo(tmp_path: pathlib.Path, **map_changes: object) -> pathlib.Path:
    """A temporary repo root whose authority map is altered in memory."""
    raw = yaml.safe_load((REPO / MAP_RELPATH).read_text(encoding="utf-8"))
    mutated = copy.deepcopy(raw)
    for dotted, value in map_changes.items():
        target = mutated
        parts = dotted.split("__")
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = value
    canonical = tmp_path / "docs" / "canonical"
    canonical.mkdir(parents=True)
    (canonical / "AUTHORITY_MAP.yaml").write_text(
        yaml.safe_dump(mutated), encoding="utf-8"
    )
    (canonical / "SECURITY_ARCHITECTURE.md").write_text(
        (REPO / SEC_RELPATH).read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def request_for(operation: str, tier: str, **overrides: object) -> PolicyRequest:
    base: dict[str, object] = {
        "operation_class": operation,
        "trust_tier": tier,
        "actor": "engineering.agent",
    }
    base.update(overrides)
    return PolicyRequest(**base)  # type: ignore[arg-type]


class TestOperationVocabularyFollowsAuthority:
    def test_removing_a_class_from_the_map_makes_it_unknown(
        self, tmp_path: pathlib.Path
    ) -> None:
        raw = yaml.safe_load((REPO / MAP_RELPATH).read_text(encoding="utf-8"))
        classes = copy.deepcopy(raw["operation_classes"])
        classes.pop("READ_FILE")
        root = mutated_repo(tmp_path, operation_classes=classes)
        vocabulary = OperationClassVocabulary.load(root)
        assert not vocabulary.contains("READ_FILE")
        assert OperationClassVocabulary.load(REPO).contains("READ_FILE")

    def test_changing_unmapped_resolution_changes_the_declared_fallback(
        self, tmp_path: pathlib.Path
    ) -> None:
        root = mutated_repo(tmp_path, unmapped_action_resolution="ASK_USER")
        assert (
            OperationClassVocabulary.load(root).unmapped_resolution
            is Decision.ASK_USER
        )
        assert (
            OperationClassVocabulary.load(REPO).unmapped_resolution is Decision.DENY
        )

    def test_an_empty_vocabulary_fails_closed(self, tmp_path: pathlib.Path) -> None:
        root = mutated_repo(tmp_path, operation_classes={})
        with pytest.raises(AuthoritativeSourceError):
            OperationClassVocabulary.load(root)

    def test_a_missing_unmapped_rule_fails_closed(
        self, tmp_path: pathlib.Path
    ) -> None:
        raw = yaml.safe_load((REPO / MAP_RELPATH).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(raw)
        mutated.pop("unmapped_action_resolution")
        canonical = tmp_path / "docs" / "canonical"
        canonical.mkdir(parents=True)
        (canonical / "AUTHORITY_MAP.yaml").write_text(
            yaml.safe_dump(mutated), encoding="utf-8"
        )
        with pytest.raises(AuthoritativeSourceError):
            OperationClassVocabulary.load(tmp_path)


class TestTrustTiersFollowAuthority:
    def test_adding_a_required_property_changes_satisfiability(
        self, tmp_path: pathlib.Path
    ) -> None:
        """No validator edited; only the authoritative tier requirement moves."""
        raw = yaml.safe_load((REPO / MAP_RELPATH).read_text(encoding="utf-8"))
        isolation = copy.deepcopy(raw["isolation"])
        isolation["tier_requirements"]["TRUST-1"] = [
            *isolation["tier_requirements"]["TRUST-1"],
            "KERNEL_ISOLATION",
        ]
        root = mutated_repo(tmp_path, isolation=isolation)

        from arkali.control.isolation.isolation_contract import BackendDescriptor
        from arkali.kernel.contracts.results import HonestState

        available = (
            BackendDescriptor(
                name="job_object",
                provides=("PROCESS_CONTAINMENT", "RESOURCE_LIMITS"),
                availability=HonestState.PASS,
            ),
            BackendDescriptor(
                name="workspace_acl",
                provides=("FS_CONFINEMENT",),
                availability=HonestState.PASS,
            ),
        )
        assert IsolationAuthority.load(REPO).resolve("TRUST-1", available).satisfied
        assert not IsolationAuthority.load(root).resolve("TRUST-1", available).satisfied

    def test_changing_a_backend_property_table_changes_the_verdict(
        self, tmp_path: pathlib.Path
    ) -> None:
        raw = yaml.safe_load((REPO / MAP_RELPATH).read_text(encoding="utf-8"))
        isolation = copy.deepcopy(raw["isolation"])
        isolation["backends"]["job_object"] = ["PROCESS_CONTAINMENT"]
        root = mutated_repo(tmp_path, isolation=isolation)
        assert IsolationAuthority.load(root).declared_backends()["job_object"] == (
            "PROCESS_CONTAINMENT",
        )
        assert "RESOURCE_LIMITS" in (
            IsolationAuthority.load(REPO).declared_backends()["job_object"]
        )


class TestProtectedCoreFollowsAuthority:
    def test_membership_follows_the_map(self, tmp_path: pathlib.Path) -> None:
        raw = yaml.safe_load((REPO / MAP_RELPATH).read_text(encoding="utf-8"))
        contexts = copy.deepcopy(raw["contexts"])
        contexts["engineering.agent"]["protected_core"] = True
        root = mutated_repo(tmp_path, contexts=contexts)
        assert "engineering.agent" in ProtectedCoreBoundary.load(root).contexts
        assert "engineering.agent" not in ProtectedCoreBoundary.load(REPO).contexts

    def test_an_empty_protected_set_fails_closed(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A boundary protecting nothing must refuse to exist."""
        raw = yaml.safe_load((REPO / MAP_RELPATH).read_text(encoding="utf-8"))
        contexts = copy.deepcopy(raw["contexts"])
        for meta in contexts.values():
            meta["protected_core"] = False
        root = mutated_repo(tmp_path, contexts=contexts)
        with pytest.raises(AuthoritativeSourceError):
            ProtectedCoreBoundary.load(root)


class TestPdpFollowsAuthority:
    def test_changing_a_fixed_rule_changes_the_decision(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The strongest drift control: the PDP is not carrying its own rules."""
        raw = yaml.safe_load((REPO / MAP_RELPATH).read_text(encoding="utf-8"))
        classes = copy.deepcopy(raw["operation_classes"])
        classes["WRITE_WORKSPACE_FILE"]["fixed"] = "DENY"
        root = mutated_repo(tmp_path, operation_classes=classes)

        live = PolicyDecisionPoint.load(REPO)
        drifted = PolicyDecisionPoint.load(root)
        request = request_for("WRITE_WORKSPACE_FILE", "TRUST-0")
        assert live.decide(request).decision is Decision.AUTO
        assert drifted.decide(request).decision is Decision.DENY

    def test_changing_the_rollback_invoker_changes_who_is_named(
        self, tmp_path: pathlib.Path
    ) -> None:
        raw = yaml.safe_load((REPO / MAP_RELPATH).read_text(encoding="utf-8"))
        mutation = copy.deepcopy(raw["stable_mutation"])
        mutation["sole_exception"]["invoker"] = "lifecycle.evolution"
        root = mutated_repo(tmp_path, stable_mutation=mutation)
        record = PolicyDecisionPoint.load(root).decide(
            request_for("ROLLBACK_STABLE", "TRUST-0")
        )
        assert "lifecycle.evolution" in record.reason
        assert record.decision is Decision.DENY


class TestMatrixAndMapAgree:
    """Reconciliation is semantic, not textual.

    The two canonical sources legitimately phrase the same rule differently:
    the map says `OWN_PROCESS_ONLY` where the document says "never
    cross-boundary", and `LOCKFILE_BOUND` where the document says "lockfile-bound
    only". Asserting textual overlap would report drift that does not exist and,
    worse, would pressure someone to edit a canonical document to satisfy a test.
    What must agree is what the rules *do*.
    """

    def test_the_two_sources_declare_the_same_vocabulary(self) -> None:
        vocabulary = OperationClassVocabulary.load(REPO)
        matrix = SecurityMatrix.load(REPO)
        assert set(vocabulary.names()) == set(matrix.operation_classes())

    def test_never_auto_classes_are_never_auto_in_the_document(self) -> None:
        vocabulary = OperationClassVocabulary.load(REPO)
        matrix = SecurityMatrix.load(REPO)
        checked = 0
        for name in vocabulary.names():
            if not vocabulary.get(name).never_auto:
                continue
            for tier in matrix.tiers():
                assert matrix.resolution(name, tier).decision is not Decision.AUTO
            checked += 1
        assert checked > 0, "no NEVER_AUTO class found; the control would be vacuous"

    def test_local_only_classes_say_so_in_the_document(self) -> None:
        vocabulary = OperationClassVocabulary.load(REPO)
        matrix = SecurityMatrix.load(REPO)
        checked = 0
        for name in vocabulary.names():
            if not vocabulary.get(name).denied_in_local_only:
                continue
            assert "LOCAL-ONLY" in matrix.fixed_rule(name).upper()
            checked += 1
        assert checked > 0

    def test_recovery_only_class_says_so_in_the_document(self) -> None:
        vocabulary = OperationClassVocabulary.load(REPO)
        matrix = SecurityMatrix.load(REPO)
        recovery = [
            n for n in vocabulary.names()
            if vocabulary.get(n).fixed == "RECOVERY_SUPERVISOR_ONLY"
        ]
        assert recovery == ["ROLLBACK_STABLE"]
        assert "RECOVERY SUPERVISOR" in matrix.fixed_rule("ROLLBACK_STABLE").upper()

    def test_deny_classes_agree(self) -> None:
        vocabulary = OperationClassVocabulary.load(REPO)
        matrix = SecurityMatrix.load(REPO)
        for name in vocabulary.names():
            if not vocabulary.get(name).is_always_denied:
                continue
            for tier in matrix.tiers():
                assert matrix.resolution(name, tier).decision is Decision.DENY


class TestNoAcceptedStateIsMutated:
    def test_loading_and_deciding_does_not_touch_canonical_files(self) -> None:
        before = {p: (REPO / p).read_bytes() for p in WATCHED}
        pdp = PolicyDecisionPoint.load(REPO)
        pdp.decide(request_for("READ_FILE", "TRUST-0"))
        IsolationAuthority.load(REPO)
        ProtectedCoreBoundary.load(REPO)
        after = {p: (REPO / p).read_bytes() for p in WATCHED}
        assert before == after
