"""Phase 26 Package 5: supply-chain negative/adversarial proofs for C-31.

Every case below names one of the risks Phase 26's own acceptance brief
lists explicitly: artifact tampering, digest mismatch, stale release
candidate, wrong provenance, unsigned/unverified package, dependency
substitution, release replay, wrong target/environment, secret leakage,
direct Stable mutation, rollback to unverified revision, package/version
identity collision, and build artifact/source mismatch. Two risks -
bypassed acceptance and bypassed release policy - are Package 6's own
subject (the real HUMAN_GATE_7 wiring); this file does not claim them
closed.

No finding here rests on a stored boolean: every proof re-derives the fact
it asserts, exactly as `sbom.py`/`release_provenance.py`'s own docstrings
already require of themselves.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import pathlib
from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import Engine

from alembic import command
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.secret_reference import RawSecretLeak
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.errors import ArtifactContentMismatch
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.lifecycle.release.release_manifest import ReleaseAuthority, ReleaseAuthorityError
from arkali.lifecycle.release.release_provenance import (
    ProvenanceFields,
    register_release_provenance,
)
from arkali.lifecycle.release.sbom import generate_sbom
from arkali.lifecycle.release.stable_path import StableCandidatePath, StageReceipt
from arkali.lifecycle.release.stable_pointer import StablePointerError, StableRevisionPointer

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
RELEASE_PACKAGE = BACKEND / "arkali" / "lifecycle" / "release"
REV_A = "sha256:" + "a" * 64
REV_B = "sha256:" + "b" * 64


class _RealArtifactRegistrar:
    def __init__(self, store: ArtifactStore) -> None:
        self._store = store

    def register(self, payload: bytes, provenance: ProvenanceFields) -> str:
        return self._store.register(
            payload,
            ProvenanceInput(
                producer_agent=provenance.producer_agent,
                provider_model=provenance.provider_model,
                task_id=provenance.task_id,
                specification_version=provenance.specification_version,
                context_hash=provenance.context_hash,
                normalization=provenance.normalization,
                tests=provenance.tests, evidence=provenance.evidence,
                parents=provenance.parents,
            ),
        )

    def verify(self, address: str) -> bool:
        return self._store.verify(address)

    def content_of(self, address: str) -> bytes:
        return self._store.content_of(address)


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "release_adversarial.db"
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(path))
    command.upgrade(config, "head")
    return path


@pytest.fixture()
def engine(database_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(database_path))
    yield built
    built.dispose()


@pytest.fixture()
def blob_pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store")


@pytest.fixture()
def blobs(tmp_path: pathlib.Path, blob_pep: PolicyEnforcementPoint) -> ArtifactBlobStore:
    return ArtifactBlobStore(tmp_path / "blobs", blob_pep)


@pytest.fixture()
def path() -> StableCandidatePath:
    return StableCandidatePath.load(REPO)


@pytest.fixture()
def pointer(path: StableCandidatePath, tmp_path: pathlib.Path) -> StableRevisionPointer:
    return StableRevisionPointer(path, tmp_path / "stable_pointer.json")


def _promotion_receipt(path: StableCandidatePath, candidate_id: str) -> StageReceipt:
    receipt = path.begin_candidate(candidate_id=candidate_id)
    for stage in path.stages()[2:-1]:
        receipt = path.advance(receipt, to_stage=stage)
    return path.promotion_receipt(receipt)


class TestArtifactTamperingAndDigestMismatch:
    def test_a_tampered_blob_fails_verification_and_refuses_content_read(
        self, engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            store = ArtifactStore(session, blobs)
            address = store.register(
                b"original release payload",
                ProvenanceInput(
                    producer_agent="test", provider_model="none", task_id="t",
                    specification_version="C-31", context_hash=REV_A,
                ),
            )
        blobs.path_for(address).write_bytes(b"tampered payload")
        with unit_of_work(create_session_factory(engine)) as session:
            store = ArtifactStore(session, blobs)
            assert store.verify(address) is False
            with pytest.raises(ArtifactContentMismatch):
                store.content_of(address)


class TestStaleOrForgedReleaseCandidate:
    def test_a_candidate_naming_a_revision_never_promoted_is_refused(
        self, path: StableCandidatePath, pointer: StableRevisionPointer,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "core-1"), revision_id=REV_A, candidate_id="core-1"
        )
        authority = ReleaseAuthority(pointer)
        candidate, _instance = authority.declare_release_candidate()
        forged = candidate.model_copy(update={"core_revision_id": REV_B})
        with pytest.raises(ReleaseAuthorityError):
            authority.assert_still_stable(forged)


class TestWrongProvenance:
    def test_provenance_context_hash_always_matches_the_real_core_revision(
        self, path: StableCandidatePath, engine: Engine,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        """A caller has no parameter by which to make the registered
        provenance disagree with the candidate's own real core revision."""
        pointer.promote(
            _promotion_receipt(path, "core-1"), revision_id=REV_A, candidate_id="core-1"
        )
        authority = ReleaseAuthority(pointer)
        candidate, _instance = authority.declare_release_candidate()
        with unit_of_work(create_session_factory(engine)) as session:
            artifacts = ArtifactStore(session, blobs)
            record = register_release_provenance(candidate, _RealArtifactRegistrar(artifacts))
            provenance = artifacts.provenance_of(record.artifact_id)
            assert provenance is not None
            assert provenance.context_hash == candidate.core_revision_id == REV_A


class TestDependencySubstitutionAndBuildArtifactSourceMismatch:
    def test_a_substituted_dependency_immediately_changes_the_sbom(
        self, tmp_path: pathlib.Path,
    ) -> None:
        backend = tmp_path / "backend"
        backend.mkdir()
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text(json.dumps({"dependencies": {}}), encoding="utf-8")
        (backend / "pyproject.toml").write_text(
            '[project]\ndependencies = ["widget>=1.0"]\n', encoding="utf-8"
        )
        before = generate_sbom(tmp_path)
        (backend / "pyproject.toml").write_text(
            '[project]\ndependencies = ["widget>=9.9.9-compromised"]\n', encoding="utf-8"
        )
        after = generate_sbom(tmp_path)
        assert before != after, "a substituted dependency must never go unnoticed"


class TestReleaseReplay:
    def test_replaying_the_same_declaration_never_creates_a_second_artifact(
        self, path: StableCandidatePath, engine: Engine,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "core-1"), revision_id=REV_A, candidate_id="core-1"
        )
        authority = ReleaseAuthority(pointer)
        now = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
        candidate, _instance = authority.declare_release_candidate(now=now)
        with unit_of_work(create_session_factory(engine)) as session:
            registrar = _RealArtifactRegistrar(ArtifactStore(session, blobs))
            replayed = [register_release_provenance(candidate, registrar) for _ in range(3)]
        assert len({r.artifact_id for r in replayed}) == 1


class TestSecretLeakage:
    def test_a_secret_shaped_provenance_field_is_refused_before_persisting(
        self, engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            store = ArtifactStore(session, blobs)
            with pytest.raises(RawSecretLeak):
                store.register(
                    b"payload",
                    ProvenanceInput(
                        producer_agent="test", provider_model="none",
                        task_id="AKIA" + "A" * 16, specification_version="C-31",
                        context_hash=REV_A,
                    ),
                )


class TestNoDirectStableMutationAnywhereInReleaseModules:
    def test_only_stable_pointer_py_ever_calls_promote_or_rollback_to(self) -> None:
        offenders: list[str] = []
        for source in sorted(RELEASE_PACKAGE.glob("*.py")):
            if source.name == "stable_pointer.py":
                continue
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in ("promote", "rollback_to"):
                    offenders.append(f"{source.name}:{node.lineno}")
        assert not offenders, f"only stable_pointer.py may mutate Stable: {offenders}"


class TestNoWrongTargetOrEnvironmentSelectionSurfaceExists:
    def test_no_release_function_accepts_a_deployment_target_parameter(self) -> None:
        """This phase's canonical scope builds no real deployment path
        (§Discovery item 12); proven structurally, not merely by absence of
        a test that would have exercised one."""
        suspicious_names = {"target", "environment", "env", "deploy_target", "host"}
        offenders: list[str] = []
        for source in sorted(RELEASE_PACKAGE.glob("*.py")):
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for arg in node.args.args + node.args.kwonlyargs:
                        if arg.arg.lower() in suspicious_names:
                            offenders.append(f"{source.name}:{node.name}:{arg.arg}")
        assert not offenders, f"no deployment-target parameter may exist yet: {offenders}"


class TestUnsignedOrUnverifiedPackageCannotReachReleased:
    def test_draft_to_released_directly_is_not_a_declared_transition(self) -> None:
        from arkali.lifecycle.release import release_state_machine as rsm
        assert ("DRAFT", "RELEASED") not in rsm.DEFINITION.transition_set
        assert ("BUILT", "RELEASED") not in rsm.DEFINITION.transition_set
        assert ("VERIFIED", "RELEASED") not in rsm.DEFINITION.transition_set
        assert ("SIGNED_READY", "RELEASED") in rsm.DEFINITION.transition_set


class TestRollbackToUnverifiedRevisionStillRefused:
    def test_lifecycle_release_introduces_no_bypass_of_the_unmodified_pointer(
        self, path: StableCandidatePath, pointer: StableRevisionPointer,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "core-1"), revision_id=REV_A, candidate_id="core-1"
        )
        with pytest.raises(StablePointerError):
            pointer.rollback_to(REV_B)


class TestPackageVersionIdentityCollision:
    def test_two_different_core_revisions_never_share_a_release_id(
        self, path: StableCandidatePath, pointer: StableRevisionPointer,
    ) -> None:
        now = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
        pointer.promote(
            _promotion_receipt(path, "core-1"), revision_id=REV_A, candidate_id="core-1"
        )
        authority = ReleaseAuthority(pointer)
        first, _ = authority.declare_release_candidate(now=now)
        pointer.promote(
            _promotion_receipt(path, "core-2"), revision_id=REV_B, candidate_id="core-2"
        )
        second, _ = authority.declare_release_candidate(now=now)
        assert first.release_id != second.release_id
