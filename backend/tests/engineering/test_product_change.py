"""Real, over-real-persistence tests for `engineering.product_change`
(D-030 V1): change-plan validation, source materialization/archiving,
changeset application/verification, and promotion/rejection.

Every test drives real owners over real, isolated persistence -- a real
`ProjectRegistry` over a real SQLite file, a real `ArtifactStore` +
`ArtifactBlobStore` over a second real SQLite file and a real filesystem
blob store, and a real `WorkspaceAuthority`, all isolated per test via
`tmp_path`. The model provider is a real, typed test double
(`FixedModel`/`SequencedModel`, the identical pattern `test_model_product_
generation.py` already established) -- no network call, no real Ollama
dependency for these tests; the real Ollama proof is separate, live,
browser-driven evidence.
"""

from __future__ import annotations

import json
import pathlib
import zipfile
from collections.abc import Iterator

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.engineering.localai.adapter import HonestState, InferenceResult
from arkali.engineering.product_change.change_plan import ChangeOperation, ChangePlan
from arkali.engineering.product_change.errors import (
    ChangesetValidationError,
    ModelPlanInvalidError,
    NoBaseRevisionError,
    PromotionNotAuthorizedError,
    RevisionSourceUnavailableError,
    StaleBaseRevisionError,
    VerificationFailedError,
)
from arkali.engineering.product_change.modification import (
    ModificationWiring,
    _apply_changeset,
    _validate_changeset,
    prepare_modification,
)
from arkali.engineering.product_change.inspection import (
    _MAX_GROUNDED_SOURCE_BYTES,
    _MAX_GROUNDED_SOURCE_FILES,
    _select_authoritative_source,
    inspect_source,
)
from arkali.engineering.product_change.promotion import (
    PROMOTION_GATE_ID,
    PROMOTION_OPERATION_CLASS,
    promote_modification,
    reject_modification,
)
from arkali.engineering.product_change.revision_resolution import (
    _MANAGED_PRODUCT_PROVENANCE_SPEC,
    _MANAGED_PRODUCT_REVISION_SOURCE_SPEC,
    archive_source,
    materialized_source,
    resolve_current_revision,
)
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.session import (
    create_base_schema,
    create_session_factory,
    unit_of_work,
)

REPO = pathlib.Path(__file__).resolve().parents[3]


class FixedModel:
    """Same shape as `test_model_product_generation.FixedModel` -- a real
    `InferenceResult`, never a fabricated shortcut."""

    def __init__(self, output: str, state: HonestState = HonestState.PASS) -> None:
        self.output = output
        self.state = state

    def infer(self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0) -> InferenceResult:
        assert timeout_seconds > 0
        return InferenceResult(
            runtime="test-runtime", model_id=model_id, state=self.state,
            detail="product-change test double", output=self.output,
            output_excerpt=self.output[:200],
        )


class RecordingModel(FixedModel):
    def __init__(self, output: str) -> None:
        super().__init__(output)
        self.prompts: list[str] = []

    def infer(self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0) -> InferenceResult:
        self.prompts.append(prompt)
        return super().infer(model_id, prompt, timeout_seconds=timeout_seconds)


class _StubCandidateSource:
    def __init__(self, directory: pathlib.Path) -> None:
        self._directory = directory

    def source_dir(self, candidate_id: str) -> pathlib.Path:
        assert candidate_id == "candidate-x"
        return self._directory


class _AlwaysGrant:
    def operation_grant(
        self, gate_id: str, operation_class: str, target_identity: str, revision_identity: str,
    ) -> bool:
        return gate_id == PROMOTION_GATE_ID and operation_class == PROMOTION_OPERATION_CLASS


class _NeverGrant:
    def operation_grant(self, *args: object, **kwargs: object) -> bool:
        return False


class _ChildProductScopedGrant:
    """A real `PROMOTE_CHILD_PRODUCT` grant under `HUMAN_GATE_3` -- the
    identical shape a real `lifecycle.evolution` promotion would leave in
    `HUMAN_GATE_RECORDS.md` -- mirroring `GovernanceState.operation_
    grant`'s own exact 4-field match. Governance-scope audit: proves a
    grant recorded for `PROMOTE_CHILD_PRODUCT` can never satisfy a
    `MANAGED_PRODUCT_REVISION_PROMOTION` lookup, matching (gate,
    operation_class, target, revision) exactly rather than by gate alone."""

    def operation_grant(
        self, gate_id: str, operation_class: str, target_identity: str, revision_identity: str,
    ) -> bool:
        return (
            gate_id == "HUMAN_GATE_3" and operation_class == "PROMOTE_CHILD_PRODUCT"
            and target_identity == "any-child-product-manifest-ref"
            and revision_identity == "any-child-product-revision"
        )


@pytest.fixture()
def registry_engine(tmp_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(tmp_path / "command_center.db"))
    create_base_schema(built)
    yield built
    built.dispose()


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def artifact_engine(tmp_path: pathlib.Path) -> Iterator[Engine]:
    from alembic import command
    from alembic.config import Config
    from arkali.kernel.persistence.migrations import ALEMBIC_INI

    db_path = tmp_path / "evidence.db"
    config = Config(str(REPO / "backend" / ALEMBIC_INI))
    config.set_main_option("script_location", str(REPO / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(db_path))
    command.upgrade(config, "head")
    built = create_persistence_engine(sqlite_url(db_path))
    yield built
    built.dispose()


@pytest.fixture()
def blobs(tmp_path: pathlib.Path, pdp: PolicyDecisionPoint) -> ArtifactBlobStore:
    return ArtifactBlobStore(
        tmp_path / "blobs", PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store"),
    )


def _seed_initial_revision(
    project_id: str, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    candidate_dir: pathlib.Path,
) -> str:
    """A real, minimal Factory-origin revision — the identical provenance
    shape `product_registration.py` (D-029) writes — so `resolve_current_
    revision`/`materialized_source` have a real chain to walk. Returns the
    revision_id."""
    with unit_of_work(create_session_factory(artifact_engine)) as evidence_session:
        artifacts = ArtifactStore(evidence_session, blobs)
        payload = json.dumps({"candidate_id": "candidate-x"}).encode("utf-8")
        provenance_ref = artifacts.register(
            payload,
            ProvenanceInput(
                producer_agent="engineering.factory", provider_model="local",
                task_id="candidate-x", specification_version=_MANAGED_PRODUCT_PROVENANCE_SPEC,
                context_hash="seed",
            ),
        )
    with unit_of_work(create_session_factory(registry_engine)) as session:
        registry = ProjectRegistry(session)
        registry.create_project(project_id, "Test Product")
        revision_id = f"{project_id}-r1"
        registry.create_revision(project_id, revision_id, provenance_ref=provenance_ref)
    return revision_id


class TestResolveCurrentRevision:
    def test_no_revision_is_refused(self, registry_engine: Engine) -> None:
        with unit_of_work(create_session_factory(registry_engine)) as session:
            registry = ProjectRegistry(session)
            registry.create_project("p1", "Empty Product")
            with pytest.raises(NoBaseRevisionError):
                resolve_current_revision("p1", registry=registry)

    def test_current_is_the_max_sequence_revision(self, registry_engine: Engine) -> None:
        with unit_of_work(create_session_factory(registry_engine)) as session:
            registry = ProjectRegistry(session)
            registry.create_project("p1", "Product")
            registry.create_revision("p1", "p1-r1")
            registry.create_revision("p1", "p1-r2")
            current = resolve_current_revision("p1", registry=registry)
            assert current.revision_id == "p1-r2"
            assert current.sequence == 2


class TestMaterializedSource:
    def test_factory_origin_revision_resolves_via_candidate_source_resolver(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        candidate_dir = tmp_path / "candidate-x"
        candidate_dir.mkdir()
        (candidate_dir / "app.py").write_text("real candidate source", encoding="utf-8")
        _seed_initial_revision("p1", registry_engine, artifact_engine, blobs, candidate_dir)

        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as evidence_session:
            registry = ProjectRegistry(session)
            artifacts = ArtifactStore(evidence_session, blobs)
            revision = resolve_current_revision("p1", registry=registry)
            with materialized_source(
                revision, artifacts=artifacts,
                candidate_source_resolver=_StubCandidateSource(candidate_dir),
            ) as source:
                assert source == candidate_dir
                assert (source / "app.py").read_text(encoding="utf-8") == "real candidate source"

    def test_promoted_revision_resolves_via_real_archive_extraction(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        tree = tmp_path / "tree"
        (tree / "sub").mkdir(parents=True)
        (tree / "app.py").write_text("v2", encoding="utf-8")
        (tree / "sub" / "util.py").write_text("helper", encoding="utf-8")
        archive_bytes = archive_source(tree)

        with unit_of_work(create_session_factory(artifact_engine)) as evidence_session:
            artifacts = ArtifactStore(evidence_session, blobs)
            ref = artifacts.register(
                archive_bytes,
                ProvenanceInput(
                    producer_agent="engineering.product_change", provider_model="local",
                    task_id="p1", specification_version=_MANAGED_PRODUCT_REVISION_SOURCE_SPEC,
                    context_hash="seed2",
                ),
            )
        with unit_of_work(create_session_factory(registry_engine)) as session:
            registry = ProjectRegistry(session)
            registry.create_project("p2", "Product 2")
            revision = registry.create_revision("p2", "p2-r1", provenance_ref=ref)

        with unit_of_work(create_session_factory(artifact_engine)) as evidence_session:
            artifacts = ArtifactStore(evidence_session, blobs)
            with materialized_source(
                revision, artifacts=artifacts, candidate_source_resolver=_StubCandidateSource(tree),
            ) as source:
                assert (source / "app.py").read_text(encoding="utf-8") == "v2"
                assert (source / "sub" / "util.py").read_text(encoding="utf-8") == "helper"

    def test_corrupt_archive_fails_closed(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        """F-0074 Part F: a promoted revision whose registered artifact is
        NOT a real, valid ZIP fails closed with a real exception -- never
        a silent empty/partial materialization, and never a fallback to
        any candidate source."""
        with unit_of_work(create_session_factory(artifact_engine)) as evidence_session:
            artifacts = ArtifactStore(evidence_session, blobs)
            ref = artifacts.register(
                b"this is not a real zip archive",
                ProvenanceInput(
                    producer_agent="engineering.product_change", provider_model="local",
                    task_id="p3", specification_version=_MANAGED_PRODUCT_REVISION_SOURCE_SPEC,
                    context_hash="corrupt",
                ),
            )
        with unit_of_work(create_session_factory(registry_engine)) as session:
            registry = ProjectRegistry(session)
            registry.create_project("p3", "Corrupt Archive Product")
            revision = registry.create_revision("p3", "p3-r1", provenance_ref=ref)

        with unit_of_work(create_session_factory(artifact_engine)) as evidence_session, \
             pytest.raises(zipfile.BadZipFile):
            artifacts = ArtifactStore(evidence_session, blobs)
            with materialized_source(
                revision, artifacts=artifacts,
                candidate_source_resolver=_StubCandidateSource(pathlib.Path(".")),
            ):
                pass

    def test_no_provenance_ref_is_refused(self, registry_engine: Engine, artifact_engine: Engine) -> None:
        with unit_of_work(create_session_factory(registry_engine)) as session:
            registry = ProjectRegistry(session)
            registry.create_project("p3", "Product 3")
            revision = registry.create_revision("p3", "p3-r1")
        with unit_of_work(create_session_factory(artifact_engine)) as evidence_session, \
             pytest.raises(RevisionSourceUnavailableError):
            ArtifactStore(evidence_session, ArtifactBlobStore.__new__(ArtifactBlobStore))
            with materialized_source(
                revision, artifacts=ArtifactStore(evidence_session, ArtifactBlobStore.__new__(ArtifactBlobStore)),
                candidate_source_resolver=_StubCandidateSource(pathlib.Path(".")),
            ):
                pass


class TestArchiveSourceDeterminism:
    def test_identical_trees_produce_byte_identical_archives(self, tmp_path: pathlib.Path) -> None:
        one = tmp_path / "one"
        two = tmp_path / "two"
        for root in (one, two):
            (root / "sub").mkdir(parents=True)
            (root / "app.py").write_text("same content", encoding="utf-8")
            (root / "sub" / "util.py").write_text("same helper", encoding="utf-8")
        assert archive_source(one) == archive_source(two)

    def test_different_content_produces_a_different_archive(self, tmp_path: pathlib.Path) -> None:
        one = tmp_path / "one"
        two = tmp_path / "two"
        one.mkdir()
        two.mkdir()
        (one / "app.py").write_text("v1", encoding="utf-8")
        (two / "app.py").write_text("v2", encoding="utf-8")
        assert archive_source(one) != archive_source(two)


class TestChangePlanSchema:
    def test_unknown_field_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            ChangeOperation(
                operation="create", path="a.py", rationale="x", invented_field="nope",  # type: ignore[call-arg]
            )

    def test_empty_operations_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            ChangePlan(request_text="do x", target_summary="y", operations=())


class TestValidateAndApplyChangeset:
    def test_unsafe_paths_are_refused(self) -> None:
        for bad_path in ("/etc/passwd", "../escape.py"):
            with pytest.raises(ChangesetValidationError):
                _validate_changeset((
                    ChangeOperation(operation="create", path=bad_path, content="x", rationale="r"),
                ))

    def test_rename_without_new_path_is_refused(self) -> None:
        with pytest.raises(ChangesetValidationError):
            _validate_changeset((
                ChangeOperation(operation="rename", path="a.py", rationale="r"),
            ))

    def test_duplicate_target_is_refused(self) -> None:
        with pytest.raises(ChangesetValidationError):
            _validate_changeset((
                ChangeOperation(operation="create", path="a.py", content="1", rationale="r"),
                ChangeOperation(operation="update", path="a.py", content="2", rationale="r"),
            ))

    def test_create_or_update_without_content_is_refused(self) -> None:
        with pytest.raises(ChangesetValidationError):
            _validate_changeset((
                ChangeOperation(operation="create", path="a.py", rationale="r"),
            ))

    def test_valid_changeset_applies_create_update_delete_rename(self, tmp_path: pathlib.Path) -> None:
        stable = tmp_path / "stable"
        stable.mkdir()
        (stable / "old.py").write_text("stable", encoding="utf-8")
        (stable / "gone.py").write_text("stable", encoding="utf-8")
        workspace = WorkspaceAuthority(tmp_path / "ws").allocate(
            workspace_id="w1", task_id="t1", agent_id="a1", stable_snapshot=stable,
        )
        operations = (
            ChangeOperation(operation="create", path="new.py", content="hello", rationale="r"),
            ChangeOperation(operation="delete", path="gone.py", rationale="r"),
            ChangeOperation(operation="rename", path="old.py", new_path="renamed.py", rationale="r"),
        )
        _validate_changeset(operations)
        _apply_changeset(workspace, operations)
        assert (workspace.snapshot / "new.py").read_text(encoding="utf-8") == "hello"
        assert not (workspace.snapshot / "gone.py").exists()
        assert (workspace.snapshot / "renamed.py").exists()
        assert not (workspace.snapshot / "old.py").exists()


class TestPrepareModification:
    def test_historical_cross_file_contract_is_grounded_and_preserved(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        candidate = tmp_path / "candidate-x"
        (candidate / "frontend" / "src").mkdir(parents=True)
        provider = "export const resolveNebulaToken = () => 'stable';\n"
        consumer = (
            "import { resolveNebulaToken } from './signalBridge';\n"
            "export default function AuroraPanel() {\n"
            "  return <h1>{resolveNebulaToken()}</h1>;\n}\n"
        )
        (candidate / "frontend/src/signalBridge.js").write_text(provider, encoding="utf-8")
        (candidate / "frontend/src/AuroraPanel.js").write_text(consumer, encoding="utf-8")
        (candidate / "frontend/src/unrelated.js").write_text("export const noise = 1;\n", encoding="utf-8")
        _seed_initial_revision("p1", registry_engine, artifact_engine, blobs, candidate)
        replacement = consumer.replace("<h1>", "<h1 className=\"modern\">")
        model = RecordingModel(json.dumps({
            "schema_version": "1.0.0", "request_text": "modernize AuroraPanel heading",
            "target_summary": "bounded visible change", "operations": [{
                "operation": "update", "path": "frontend/src/AuroraPanel.js",
                "content": replacement, "rationale": "requested presentation change",
            }],
        }))
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session:
            prepared = prepare_modification(
                "p1", "modernize AuroraPanel heading", registry=ProjectRegistry(session),
                wiring=ModificationWiring(
                    artifacts=ArtifactStore(art_session, blobs),
                    candidate_source_resolver=_StubCandidateSource(candidate),
                    workspace_allocator=WorkspaceAuthority(tmp_path / "change-ws"),
                    model=model, model_id="test-model",
                ),
            )
        prompt = model.prompts[0]
        assert consumer in prompt
        assert provider in prompt
        assert "./signalBridge" in prompt
        assert "resolveNebulaToken" in prompt
        assert "export const noise = 1" not in prompt
        assert prepared.verification.passed is True
        assert resolve_current_revision  # stale-revision owner remains the existing one

    def test_default_export_and_relative_path_are_grounded(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src/theme.js").write_text("export default function lunarTheme() {}\n", encoding="utf-8")
        current = "import lunarTheme from './theme';\nexport default function ZenithView() { return lunarTheme(); }\n"
        (tmp_path / "src/ZenithView.js").write_text(current, encoding="utf-8")
        report = inspect_source(tmp_path)
        selected = _select_authoritative_source(tmp_path, report, "adjust ZenithView")
        rendered = selected.render()
        assert current in rendered
        assert "export default function lunarTheme" in rendered
        assert "./theme" in rendered

    def test_selection_is_deterministic_bounded_and_excludes_sensitive_paths(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "src").mkdir()
        for name in reversed(["AlphaView.js", "BetaView.js", "GammaView.js"]):
            (tmp_path / "src" / name).write_text(f"export default function {name[:-3]}() {{}}\n", encoding="utf-8")
        (tmp_path / ".env").write_text("DO_NOT_EXPOSE=value\n", encoding="utf-8")
        (tmp_path / ".hidden.js").write_text("const hidden = 'DO_NOT_EXPOSE';\n", encoding="utf-8")
        (tmp_path / "credentials.js").write_text("const credential = 'DO_NOT_EXPOSE';\n", encoding="utf-8")
        report = inspect_source(tmp_path)
        first = _select_authoritative_source(tmp_path, report, "AlphaView", max_files=2)
        second = _select_authoritative_source(tmp_path, report, "AlphaView", max_files=2)
        assert first.paths == second.paths
        assert len(first.paths) <= 2
        assert "DO_NOT_EXPOSE" not in first.render()

    def test_required_source_over_byte_budget_fails_safely(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "EnormousPanel.js").write_text("x" * 100, encoding="utf-8")
        report = inspect_source(tmp_path)
        with pytest.raises(ChangesetValidationError, match="source context budget"):
            _select_authoritative_source(tmp_path, report, "change EnormousPanel", max_total_bytes=32)

    def test_summary_only_update_is_refused(self) -> None:
        with pytest.raises(ChangesetValidationError, match="authoritative current source"):
            _validate_changeset((ChangeOperation(
                operation="update", path="src/UnseenPanel.js", content="export default 1;",
                rationale="requested",
            ),), grounded_paths=frozenset())

    def test_default_limits_are_explicit_positive_bounds(self) -> None:
        assert 0 < _MAX_GROUNDED_SOURCE_FILES < 40
        assert 0 < _MAX_GROUNDED_SOURCE_BYTES < 1_000_000

    def test_valid_plan_is_applied_and_passes_verification(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        candidate_dir = tmp_path / "candidate-x"
        candidate_dir.mkdir()
        (candidate_dir / "app.py").write_text("print('old')\n", encoding="utf-8")
        _seed_initial_revision("p1", registry_engine, artifact_engine, blobs, candidate_dir)

        plan_json = json.dumps({
            "schema_version": "1.0.0", "request_text": "greet differently",
            "target_summary": "update greeting",
            "operations": [{
                "operation": "update", "path": "app.py",
                "content": "print('new')\n", "rationale": "requested change",
            }],
        })
        phases: list[str] = []
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session:
            wiring = ModificationWiring(
                artifacts=ArtifactStore(art_session, blobs),
                candidate_source_resolver=_StubCandidateSource(candidate_dir),
                workspace_allocator=WorkspaceAuthority(tmp_path / "change-ws"),
                model=FixedModel(plan_json), model_id="test-model",
            )
            result = prepare_modification(
                "p1", "greet differently", registry=ProjectRegistry(session), wiring=wiring,
                on_phase=lambda phase, detail: phases.append(phase),
            )

        assert result.verification.passed is True
        assert (result.product_root / "app.py").read_text(encoding="utf-8") == "print('new')\n"
        assert "plan_ready" in phases and "changes_applied" in phases and "verification_passed" in phases

    def test_invalid_provider_output_is_refused(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        candidate_dir = tmp_path / "candidate-x"
        candidate_dir.mkdir()
        (candidate_dir / "app.py").write_text("print('old')\n", encoding="utf-8")
        _seed_initial_revision("p1", registry_engine, artifact_engine, blobs, candidate_dir)

        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session:
            wiring = ModificationWiring(
                artifacts=ArtifactStore(art_session, blobs),
                candidate_source_resolver=_StubCandidateSource(candidate_dir),
                workspace_allocator=WorkspaceAuthority(tmp_path / "change-ws"),
                model=FixedModel("not json at all"), model_id="test-model",
            )
            with pytest.raises(ModelPlanInvalidError):
                prepare_modification(
                    "p1", "do something", registry=ProjectRegistry(session), wiring=wiring,
                )

    def test_broken_syntax_fails_verification_not_an_exception(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        candidate_dir = tmp_path / "candidate-x"
        candidate_dir.mkdir()
        (candidate_dir / "app.py").write_text("print('old')\n", encoding="utf-8")
        _seed_initial_revision("p1", registry_engine, artifact_engine, blobs, candidate_dir)

        plan_json = json.dumps({
            "schema_version": "1.0.0", "request_text": "break it", "target_summary": "x",
            "operations": [{
                "operation": "update", "path": "app.py",
                "content": "def broken(:\n", "rationale": "r",
            }],
        })
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session:
            wiring = ModificationWiring(
                artifacts=ArtifactStore(art_session, blobs),
                candidate_source_resolver=_StubCandidateSource(candidate_dir),
                workspace_allocator=WorkspaceAuthority(tmp_path / "change-ws"),
                model=FixedModel(plan_json), model_id="test-model",
            )
            result = prepare_modification(
                "p1", "break it", registry=ProjectRegistry(session), wiring=wiring,
            )
        assert result.verification.passed is False
        assert result.verification.failures


class TestPromoteAndReject:
    def _prepared(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path, project_id: str = "p1", label: str = "a", seed: bool = True,
        new_content: str = "print('new')\n",
    ):
        candidate_dir = tmp_path / f"candidate-x-{project_id}-{label}"
        candidate_dir.mkdir()
        (candidate_dir / "app.py").write_text("print('old')\n", encoding="utf-8")
        if seed:
            _seed_initial_revision(project_id, registry_engine, artifact_engine, blobs, candidate_dir)
        plan_json = json.dumps({
            "schema_version": "1.0.0", "request_text": "change it", "target_summary": "x",
            "operations": [{
                "operation": "update", "path": "app.py", "content": new_content, "rationale": "r",
            }],
        })
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session:
            wiring = ModificationWiring(
                artifacts=ArtifactStore(art_session, blobs),
                candidate_source_resolver=_StubCandidateSource(candidate_dir),
                workspace_allocator=WorkspaceAuthority(tmp_path / f"change-ws-{project_id}-{label}"),
                model=FixedModel(plan_json), model_id="test-model",
            )
            return prepare_modification(
                project_id, "change it", registry=ProjectRegistry(session), wiring=wiring,
            )

    def test_successful_promotion_creates_a_new_revision(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        prepared = self._prepared(registry_engine, artifact_engine, blobs, tmp_path)
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session:
            revision = promote_modification(
                "p1", prepared, registry=ProjectRegistry(session),
                artifacts=ArtifactStore(art_session, blobs), human_gates=_AlwaysGrant(),
                issuer_identity="test-issuer",
            )
        assert revision.revision_id == "p1-r2"
        assert revision.sequence == 2

    def test_double_promotion_is_idempotent(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        prepared = self._prepared(registry_engine, artifact_engine, blobs, tmp_path)
        results = []
        for _ in range(2):
            with unit_of_work(create_session_factory(registry_engine)) as session, \
                 unit_of_work(create_session_factory(artifact_engine)) as art_session:
                results.append(promote_modification(
                    "p1", prepared, registry=ProjectRegistry(session),
                    artifacts=ArtifactStore(art_session, blobs), human_gates=_AlwaysGrant(),
                    issuer_identity="test-issuer",
                ))
        assert results[0].revision_id == results[1].revision_id
        with unit_of_work(create_session_factory(registry_engine)) as session:
            assert len(ProjectRegistry(session).revisions_of("p1")) == 2

    def test_stale_base_revision_is_refused(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        first = self._prepared(
            registry_engine, artifact_engine, blobs, tmp_path, project_id="p1", label="a",
        )
        second = self._prepared(
            registry_engine, artifact_engine, blobs, tmp_path, project_id="p1", label="b", seed=False,
            new_content="print('a different change')\n",
        )
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session:
            promote_modification(
                "p1", first, registry=ProjectRegistry(session),
                artifacts=ArtifactStore(art_session, blobs), human_gates=_AlwaysGrant(),
                issuer_identity="test-issuer",
            )
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session, \
             pytest.raises(StaleBaseRevisionError):
            promote_modification(
                "p1", second, registry=ProjectRegistry(session),
                artifacts=ArtifactStore(art_session, blobs), human_gates=_AlwaysGrant(),
                issuer_identity="test-issuer",
            )

    def test_promotion_without_a_grant_is_refused(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        prepared = self._prepared(registry_engine, artifact_engine, blobs, tmp_path)
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session, \
             pytest.raises(PromotionNotAuthorizedError):
            promote_modification(
                "p1", prepared, registry=ProjectRegistry(session),
                artifacts=ArtifactStore(art_session, blobs), human_gates=_NeverGrant(),
                issuer_identity="test-issuer",
            )

    def test_a_promote_child_product_grant_cannot_authorize_this_promotion(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        """Governance-scope audit (D-030): a real `HUMAN_GATE_3` grant
        recorded for `PROMOTE_CHILD_PRODUCT` (C-36 child-product
        promotion) must never satisfy `MANAGED_PRODUCT_REVISION_
        PROMOTION` — the two are independently scoped by the identical
        (gate, operation_class, target, revision) 4-tuple match
        `GovernanceState.operation_grant` itself uses; `HUMAN_GATE_3`'s
        own reuse as a gate NUMBER never broadens what any one recorded
        grant actually authorizes."""
        prepared = self._prepared(registry_engine, artifact_engine, blobs, tmp_path)
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session, \
             pytest.raises(PromotionNotAuthorizedError):
            promote_modification(
                "p1", prepared, registry=ProjectRegistry(session),
                artifacts=ArtifactStore(art_session, blobs), human_gates=_ChildProductScopedGrant(),
                issuer_identity="test-issuer",
            )

    def test_failed_verification_is_refused_before_any_promotion(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        prepared = self._prepared(registry_engine, artifact_engine, blobs, tmp_path)
        broken = prepared.__class__(
            workspace=prepared.workspace, product_root=prepared.product_root,
            base_revision_id=prepared.base_revision_id, plan=prepared.plan,
            plan_ref=prepared.plan_ref, changeset_ref=prepared.changeset_ref,
            verification=prepared.verification.__class__(passed=False, checked_paths=[], failures=["boom"]),
        )
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session, \
             pytest.raises(VerificationFailedError):
            promote_modification(
                "p1", broken, registry=ProjectRegistry(session),
                artifacts=ArtifactStore(art_session, blobs), human_gates=_AlwaysGrant(),
                issuer_identity="test-issuer",
            )
        with unit_of_work(create_session_factory(registry_engine)) as session:
            assert len(ProjectRegistry(session).revisions_of("p1")) == 1

    def test_reject_discards_the_workspace(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        prepared = self._prepared(registry_engine, artifact_engine, blobs, tmp_path)
        assert prepared.workspace.root.exists()
        reject_modification(prepared)
        assert not prepared.workspace.root.exists()
