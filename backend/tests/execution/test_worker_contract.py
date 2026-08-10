"""C-21 worker contract behaviour and refusals (Phase 8 Package 1).

REAL MECHANISMS ONLY. A real PDP loaded from the canonical authority map and a
real PEP. The denial case flips governed *data* in a copied authority map and
keeps both mechanisms, so a refusal here is the shipping refusal rather than a
stand-in object raising - the `durable_harness.denying_pep` precedent.

NOTHING IS TRANSCRIBED. The seven worker classes, the five TRUST tiers and the
seven isolation properties are read from their canonical authorities inside the
tests, so a canonical change moves these controls with it instead of leaving
them asserting a stale list (the F-0032 pattern).

NO CLOCK IS SLEPT ON. The heartbeat interval is a declared value; every
assertion about it is a comparison.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import shutil

import pytest
import yaml
from pydantic import ValidationError

from arkali.control.isolation.isolation_contract import IsolationAuthority
from arkali.control.isolation.isolation_errors import TrustTierViolation
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_errors import PolicyDenied
from arkali.execution.scheduler.errors import (
    DuplicateWorkerDeclaration,
    ForgedIsolationRequirement,
    InvalidWorkerDeclaration,
    UndeclaredWorkerClass,
    UnknownWorkerClass,
)
from arkali.execution.scheduler.worker_contract import (
    READ,
    WorkerContract,
    WorkerDeclaration,
)
from arkali.execution.scheduler.worker_vocabulary import WorkerVocabulary

REPO = pathlib.Path(__file__).resolve().parents[3]

#: Canonical documents the contract needs: three for a real PDP, one for the
#: worker vocabulary.
DOCUMENTS = (
    "docs/canonical/AUTHORITY_MAP.yaml",
    "docs/canonical/SECURITY_ARCHITECTURE.md",
    "docs/canonical/ARCHITECTURE.md",
    "docs/canonical/EXECUTION_AND_CAPABILITY.md",
)


def _copy_canon(root: pathlib.Path) -> None:
    for relative in DOCUMENTS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)


@pytest.fixture
def pep() -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(
        PolicyDecisionPoint.load(REPO), "execution.scheduler.worker_contract"
    )


@pytest.fixture
def contract(pep: PolicyEnforcementPoint) -> WorkerContract:
    return WorkerContract(REPO, pep)


@pytest.fixture
def vocabulary() -> WorkerVocabulary:
    return WorkerVocabulary.load(REPO)


@pytest.fixture
def isolation() -> IsolationAuthority:
    return IsolationAuthority.load(REPO)


def declaration(worker_class: str, **overrides: object) -> WorkerDeclaration:
    """A valid declaration for one class, with targeted overrides."""
    fields: dict[str, object] = {
        "worker_class": worker_class,
        "concurrency_limit": 2,
        "resource_profile": "standard",
        "required_trust_tier": "TRUST-1",
        "required_isolation_properties": ("FS_CONFINEMENT",),
        "heartbeat_interval": dt.timedelta(seconds=30),
    }
    fields.update(overrides)
    return WorkerDeclaration(**fields)  # type: ignore[arg-type]


def denying_contract(root: pathlib.Path) -> WorkerContract:
    """A real PEP over a real PDP whose authority map denies `READ_FILE`."""
    _copy_canon(root)
    path = root / "docs/canonical/AUTHORITY_MAP.yaml"
    mapping = yaml.safe_load(path.read_text(encoding="utf-8"))
    mapping["operation_classes"][READ] = {"default": "DENY", "fixed": "DENY"}
    path.write_text(yaml.safe_dump(mapping), encoding="utf-8")
    return WorkerContract(
        root, PolicyEnforcementPoint(PolicyDecisionPoint.load(root), "denied")
    )


class TestCanonicalConformance:
    """Every canonical class must be expressible; nothing else may be."""

    def test_all_canonical_worker_classes_can_be_declared_and_read_back(
        self, contract: WorkerContract, vocabulary: WorkerVocabulary
    ) -> None:
        classes = vocabulary.classes()
        assert len(classes) >= 7, "canonical class list looks truncated"
        for name in classes:
            contract.declare(declaration(name))
        assert contract.declared_classes() == tuple(sorted(classes))
        for name in classes:
            assert contract.require(name).worker_class == name

    def test_every_canonical_trust_tier_is_declarable(
        self, contract: WorkerContract, isolation: IsolationAuthority,
        vocabulary: WorkerVocabulary,
    ) -> None:
        """A tier the canonical set defines may not be refused by C-21."""
        tiers = isolation.tiers
        assert len(tiers) >= 5, "canonical tier list looks truncated"
        for tier, name in zip(tiers, vocabulary.classes(), strict=False):
            recorded = contract.declare(
                declaration(name, required_trust_tier=tier)
            )
            assert recorded.required_trust_tier == tier

    def test_every_canonical_isolation_property_is_declarable(
        self, contract: WorkerContract, isolation: IsolationAuthority,
        vocabulary: WorkerVocabulary,
    ) -> None:
        properties = isolation.properties
        assert len(properties) >= 7, "canonical property list looks truncated"
        recorded = contract.declare(
            declaration(
                vocabulary.classes()[0], required_isolation_properties=properties
            )
        )
        assert set(recorded.required_isolation_properties) == set(properties)

    def test_the_read_is_deterministic(
        self, contract: WorkerContract, vocabulary: WorkerVocabulary
    ) -> None:
        name = vocabulary.classes()[0]
        contract.declare(declaration(name, concurrency_limit=7))
        first = contract.require(name)
        assert contract.require(name) == first
        assert contract.require(name).concurrency_limit == 7

    def test_canonical_classes_are_read_live_from_the_document(
        self, contract: WorkerContract, vocabulary: WorkerVocabulary
    ) -> None:
        assert contract.canonical_classes() == vocabulary.classes()


class TestDeclarationRefusals:
    """Each refusal asserts its own type, so none can pass for another reason."""

    def test_unknown_worker_class_is_refused(
        self, contract: WorkerContract
    ) -> None:
        with pytest.raises(UnknownWorkerClass):
            contract.declare(declaration("gpu-farm"))

    def test_a_class_that_is_canonical_only_after_normalisation_is_refused(
        self, contract: WorkerContract
    ) -> None:
        """Canonical spelling is exact: a second spelling is a second vocabulary."""
        for spelling in ("Agent", "build_test", "local-ai", "computer use"):
            with pytest.raises(UnknownWorkerClass):
                contract.declare(declaration(spelling))

    @pytest.mark.parametrize("limit", [0, -1, -100])
    def test_a_non_positive_concurrency_limit_is_refused(
        self, contract: WorkerContract, vocabulary: WorkerVocabulary, limit: int
    ) -> None:
        with pytest.raises(InvalidWorkerDeclaration):
            contract.declare(
                declaration(vocabulary.classes()[0], concurrency_limit=limit)
            )

    @pytest.mark.parametrize("profile", ["", "   ", "\t\n"])
    def test_an_empty_resource_profile_is_refused(
        self, contract: WorkerContract, vocabulary: WorkerVocabulary, profile: str
    ) -> None:
        with pytest.raises(InvalidWorkerDeclaration):
            contract.declare(
                declaration(vocabulary.classes()[0], resource_profile=profile)
            )

    @pytest.mark.parametrize("seconds", [0, -1, -3600])
    def test_a_non_positive_heartbeat_interval_is_refused(
        self, contract: WorkerContract, vocabulary: WorkerVocabulary, seconds: int
    ) -> None:
        with pytest.raises(InvalidWorkerDeclaration):
            contract.declare(
                declaration(
                    vocabulary.classes()[0],
                    heartbeat_interval=dt.timedelta(seconds=seconds),
                )
            )

    def test_an_unknown_trust_tier_raises_the_isolation_authoritys_own_type(
        self, contract: WorkerContract, vocabulary: WorkerVocabulary
    ) -> None:
        """`control.isolation` owns the tier vocabulary; its refusal is not reskinned."""
        with pytest.raises(TrustTierViolation):
            contract.declare(
                declaration(vocabulary.classes()[0], required_trust_tier="TRUST-9")
            )

    def test_a_forged_isolation_property_is_refused(
        self, contract: WorkerContract, vocabulary: WorkerVocabulary
    ) -> None:
        with pytest.raises(ForgedIsolationRequirement):
            contract.declare(
                declaration(
                    vocabulary.classes()[0],
                    required_isolation_properties=("TOTAL_ISOLATION",),
                )
            )

    def test_a_repeated_isolation_property_is_refused(
        self, contract: WorkerContract, vocabulary: WorkerVocabulary
    ) -> None:
        with pytest.raises(InvalidWorkerDeclaration):
            contract.declare(
                declaration(
                    vocabulary.classes()[0],
                    required_isolation_properties=(
                        "FS_CONFINEMENT", "FS_CONFINEMENT",
                    ),
                )
            )

    def test_a_second_declaration_for_one_class_is_refused(
        self, contract: WorkerContract, vocabulary: WorkerVocabulary
    ) -> None:
        name = vocabulary.classes()[0]
        contract.declare(declaration(name, concurrency_limit=1))
        with pytest.raises(DuplicateWorkerDeclaration):
            contract.declare(declaration(name, concurrency_limit=99))
        assert contract.require(name).concurrency_limit == 1

    def test_an_undeclared_canonical_class_fails_closed(
        self, contract: WorkerContract, vocabulary: WorkerVocabulary
    ) -> None:
        """No synthesised default: an absent declaration is an open question."""
        with pytest.raises(UndeclaredWorkerClass):
            contract.require(vocabulary.classes()[0])

    def test_requiring_a_non_canonical_class_is_refused_as_unknown(
        self, contract: WorkerContract
    ) -> None:
        with pytest.raises(UnknownWorkerClass):
            contract.require("gpu-farm")


class TestDeclarationShape:
    """C-21 has exactly six dimensions; a declaration may not reshape itself."""

    def test_a_seventh_dimension_is_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            WorkerDeclaration(  # type: ignore[call-arg]
                worker_class="agent",
                concurrency_limit=1,
                resource_profile="standard",
                required_trust_tier="TRUST-0",
                required_isolation_properties=(),
                heartbeat_interval=dt.timedelta(seconds=1),
                queue_priority=5,
            )

    @pytest.mark.parametrize(
        "missing",
        [
            "worker_class", "concurrency_limit", "resource_profile",
            "required_trust_tier", "heartbeat_interval",
        ],
    )
    def test_a_missing_dimension_is_refused(self, missing: str) -> None:
        fields: dict[str, object] = {
            "worker_class": "agent",
            "concurrency_limit": 1,
            "resource_profile": "standard",
            "required_trust_tier": "TRUST-0",
            "heartbeat_interval": dt.timedelta(seconds=1),
        }
        del fields[missing]
        with pytest.raises(ValidationError):
            WorkerDeclaration(**fields)  # type: ignore[arg-type]

    def test_a_declaration_is_frozen(self) -> None:
        declared = declaration("agent")
        with pytest.raises(ValidationError):
            declared.concurrency_limit = 99  # type: ignore[misc]


class TestPolicyEnforcement:
    """A denial must stop the governed read, not annotate it."""

    def test_a_denied_declaration_is_refused(self, tmp_path: pathlib.Path) -> None:
        denied = denying_contract(tmp_path)
        with pytest.raises(PolicyDenied):
            denied.declare(declaration("agent"))

    def test_a_denied_read_is_refused(self, tmp_path: pathlib.Path) -> None:
        denied = denying_contract(tmp_path)
        with pytest.raises(PolicyDenied):
            denied.require("agent")
        with pytest.raises(PolicyDenied):
            denied.canonical_classes()

    def test_a_denial_produces_no_shadow_result(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Refused work must leave nothing behind that a caller could read."""
        denied = denying_contract(tmp_path)
        with pytest.raises(PolicyDenied):
            denied.declare(declaration("agent"))
        assert denied.declared_classes() == ()

    def test_the_decision_is_audited(self, contract: WorkerContract,
                                     pep: PolicyEnforcementPoint) -> None:
        """Every decision is audited, including AUTO."""
        contract.declare(declaration("agent"))
        assert pep.audit_trail, "a governed operation left no audit record"
        assert all(record.operation_class == READ for record in pep.audit_trail)

    def test_the_pep_is_injected_with_no_default(self) -> None:
        """A caller cannot obtain a contract that reads without a decision."""
        with pytest.raises(TypeError):
            WorkerContract(REPO)  # type: ignore[call-arg]


class TestPackageTwoIsNotHere:
    """Package 1 represents declarations. It admits nothing."""

    def test_the_contract_exposes_no_admission_operation(self) -> None:
        forbidden = (
            "admit", "admission", "schedule", "allocate", "dispatch", "run",
            "claim", "lease", "enqueue", "dequeue", "priority", "fairness",
            "autoscale", "budget", "capability",
        )
        public = [name for name in dir(WorkerContract) if not name.startswith("_")]
        for name in public:
            assert not any(word in name.lower() for word in forbidden), (
                f"{name!r} is Package 2 or later behaviour"
            )

    def test_declaring_every_class_still_yields_no_admission_verdict(
        self, contract: WorkerContract, vocabulary: WorkerVocabulary
    ) -> None:
        """The whole fleet declared is still only declarations."""
        for name in vocabulary.classes():
            contract.declare(declaration(name))
        for name in vocabulary.classes():
            resolved = contract.require(name)
            assert isinstance(resolved, WorkerDeclaration)
            assert not hasattr(resolved, "admitted")
            assert not hasattr(resolved, "decision")
