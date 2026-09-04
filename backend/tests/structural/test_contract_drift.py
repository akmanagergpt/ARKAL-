"""Backend/frontend contract-drift control.

THE PROBLEM THIS SOLVES. The frontend declares the shape of every message it
exchanges with `surfaces.command`. Nothing in either toolchain connects those
declarations to the backend's actual contract: rename `lifecycle_state` to
`state` in a Pydantic model and Python stays green, TypeScript stays green, the
Vite build stays green, and the interface silently renders `undefined` in a
browser nobody is watching.

HOW IT IS DETECTED. The expected shapes are derived from the *running
application* - the OpenAPI document a real `create_app` produces, and the
Pydantic model the refusal path actually serialises - and compared field by
field, and type by type, against the interfaces declared in
`frontend/src/api/contracts.ts`. Route templates are compared the same way,
against the paths FastAPI registered.

WHY NOT A NAME OR STRING CHECK. Asserting that a file mentions `project_id`
proves nothing: it stays true after the backend stops sending it. The comparison
is against generated truth, so it cannot survive a rename on either side.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any, Final

import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.engineering.localai import host_probe
from arkali.execution.durable.recovery import JobRecovery
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.surfaces.command import contracts, factory, factory_history, workflow_contracts
from arkali.surfaces.command.contracts import (
    BACKEND_ONLY,
    BROWSER_SLICE,
    ROUTE_AUDIENCES,
    ErrorResponse,
)
from arkali.surfaces.command.app import _CommandExtensions, create_app
from arkali.surfaces.operations import contracts as operations_contracts
from tests.structural.typescript_reader import (
    FRONTEND_SRC,
    REPO,
    interfaces_of,
    read,
    strip_comments,
)

CONTRACTS_TS: Final[pathlib.Path] = FRONTEND_SRC / "api" / "contracts.ts"
CLIENT_TS: Final[pathlib.Path] = FRONTEND_SRC / "api" / "client.ts"

#: `{ method: 'GET', path: '/api/health' }` in the client's ENDPOINTS table.
_ENDPOINT = re.compile(r"method:\s*'(?P<method>\w+)',\s*path:\s*'(?P<path>[^']+)'")


def _workflow_wiring(pdp: PolicyDecisionPoint):
    """Build the C-20 composition-root wiring `create_app` accepts.

    This test module lives outside `backend/arkali/` and outside the measured
    architecture graph, exactly like `scripts/run_command_center.py` and
    `tests/surfaces/test_command_workflow_api.py` - a direct import of
    `execution.workflow` here composes the real objects without adding an edge
    the architecture budget would ever see.
    """
    from arkali.control.policy.workflow_approval import WorkflowApprovalGate
    from arkali.execution.workflow.executor import WorkflowExecutor
    from arkali.execution.workflow.graph_model import WorkflowEdge, WorkflowGraphDocument, WorkflowNode
    from arkali.execution.workflow.graph_store import WorkflowGraphStore
    from arkali.execution.workflow.graph_vocabulary import GraphVocabulary

    vocabulary = GraphVocabulary.load(REPO)
    approval_gate = WorkflowApprovalGate.load(REPO)

    def document_builder(workflow_id, nodes, edges):
        return WorkflowGraphDocument.build(
            vocabulary, workflow_id,
            nodes=[WorkflowNode(**n) for n in nodes],
            edges=[WorkflowEdge(**e) for e in edges],
        )

    def graph_store_factory(session):
        from arkali.control.policy.pep import PolicyEnforcementPoint

        return WorkflowGraphStore(
            session, PolicyEnforcementPoint(pdp, "execution.workflow.graph_store"), vocabulary
        )

    def executor_factory(session):
        return WorkflowExecutor(session, pdp, vocabulary, approval_gate)

    return document_builder, graph_store_factory, executor_factory


def _operations_wiring(pdp: PolicyDecisionPoint):
    """The real C-34 wiring, mirroring `scripts/run_command_center.py`'s own
    `_operations_wiring` and `tests/surfaces/test_command_operations_api.py`'s
    identical fixture - so the drift control exercises the same `/snapshot`
    route (`ARK-REQ-0396`, D-028) a real caller reaches, not a narrower stand-in.
    """
    from arkali.control.policy.workflow_approval import WorkflowApprovalGate
    from arkali.execution.workflow.executor import WorkflowExecutor
    from arkali.execution.workflow.graph_vocabulary import GraphVocabulary

    vocabulary = GraphVocabulary.load(REPO)
    approval_gate = WorkflowApprovalGate.load(REPO)

    def job_recovery_factory(session):
        pep = PolicyEnforcementPoint(pdp, "execution.durable.execution")
        return JobRecovery(session, pep)

    def executor_factory(session):
        return WorkflowExecutor(session, pdp, vocabulary, approval_gate)

    return job_recovery_factory, executor_factory, pdp, host_probe.probe_host


def _factory_submitter_wiring(pdp: PolicyDecisionPoint):
    """Mirrors `scripts/run_command_center.py`'s own `_factory_submitter`
    exactly, so `/api/factory/goals` is drift-tested against the same real
    `ProductionFactory` composition a live caller reaches - not a narrower
    stand-in. No `capability_query` is supplied here either: the real
    launcher wires none today, and this fixture must not silently claim a
    capability the running application does not have.
    """
    from arkali.control.architecture.authority_map import AuthorityMap
    from arkali.control.policy.pep import PolicyEnforcementPoint
    from arkali.engineering.factory.production_orchestration import (
        ProductionFactory,
        ProductionGoalRequest,
    )
    from arkali.execution.durable.job_store import JobStore, JobSubmission

    class _DurableFactorySink:
        def __init__(self, store: JobStore) -> None:
            self._store = store

        def enqueue(self, request_id: str, payload: dict[str, object]) -> str:
            record = self._store.submit(JobSubmission(
                job_id=request_id, job_type="software_factory.production",
                idempotency_key=request_id, payload=payload,
            ))
            return record.job_id

    factory = ProductionFactory(AuthorityMap.load(REPO))

    def submit(session, body):  # noqa: ANN001
        pep = PolicyEnforcementPoint(pdp, "execution.durable.job_store")
        request = ProductionGoalRequest(**body.model_dump())
        return factory.submit_goal(request, _DurableFactorySink(JobStore(session, pep)))

    return submit


def _factory_history_wiring(var_root: pathlib.Path):
    """Mirrors `scripts/run_command_center.py`'s own `_factory_candidate_
    history`/`_factory_campaign_history` exactly, over an isolated root -
    the identical shape `_operations_wiring` above already establishes for
    its own route."""
    from arkali.engineering.candidate.campaign_budget import (
        CampaignBudget, GenerationCampaignLedger, list_campaign_ids,
    )
    from arkali.engineering.candidate.ledger import CandidateLedger
    from arkali.surfaces.command.factory_history import (
        FactoryCampaignAttempt, FactoryCampaignSummary, FactoryCandidateSummary,
    )

    ledger = CandidateLedger(var_root / "factory" / "candidates" / "_ledger")
    campaigns_root = var_root / "factory" / "campaigns"

    def candidate_history():
        return tuple(
            FactoryCandidateSummary(
                candidate_id=cid, state=ledger.classify(cid),
                recorded_at=str((ledger.latest(cid) or {}).get("recorded_at", "")),
            )
            for cid in ledger.all_candidate_ids()
        )

    def campaign_history():
        summaries = []
        for campaign_id in list_campaign_ids(campaigns_root):
            campaign = GenerationCampaignLedger.load_or_create(
                campaigns_root, campaign_id, CampaignBudget(),
            )
            summaries.append(FactoryCampaignSummary(
                campaign_id=campaign_id,
                max_new_candidates=campaign.budget.max_new_candidates,
                max_total_seconds=campaign.budget.max_total_seconds,
                max_same_fingerprint_repeats=campaign.budget.max_same_fingerprint_repeats,
                consumed_candidates=campaign.consumed_candidates,
                consumed_seconds=campaign.consumed_seconds,
                status=campaign.status(),
                attempts=tuple(
                    FactoryCampaignAttempt(
                        candidate_id=str(a["candidate_id"]), outcome=str(a["outcome"]),
                        failure_class=a.get("failure_class"), fingerprint=a.get("fingerprint"),
                        elapsed_seconds=float(a["elapsed_seconds"]), recorded_at=str(a["recorded_at"]),
                    )
                    for a in campaign.attempts()
                ),
            ))
        return tuple(summaries)

    return candidate_history, campaign_history


def _preview_bridge_wiring(pdp: PolicyDecisionPoint, var_root: pathlib.Path):
    """Mirrors `scripts/run_command_center.py`'s own `_preview_bridge_
    wiring` exactly, over an isolated root — so `/api/projects/{id}/preview`
    is drift-tested against the same real composition a live caller
    reaches, not omitted as though it were still unauthorized."""
    from alembic import command
    from alembic.config import Config
    from arkali.engineering.candidate.ledger import CandidateLedger
    from arkali.evidence.artifact.blob_store import ArtifactBlobStore
    from arkali.kernel.persistence.migrations import ALEMBIC_INI
    from arkali.kernel.persistence.session import create_session_factory, unit_of_work
    from arkali.surfaces.command.product_preview_resolution import _PreviewBridgeWiring

    evidence_db = var_root / "evidence.db"
    config = Config(str(REPO / "backend" / ALEMBIC_INI))
    config.set_main_option("script_location", str(REPO / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(evidence_db))
    command.upgrade(config, "head")
    evidence_factory = create_session_factory(create_persistence_engine(sqlite_url(evidence_db)))

    def artifact_session_scope():
        with unit_of_work(evidence_factory) as session:
            yield session

    blobs = ArtifactBlobStore(
        var_root / "blobs", PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store"),
    )
    ledger = CandidateLedger(var_root / "candidates" / "_ledger")
    return _PreviewBridgeWiring(
        artifact_session_scope=artifact_session_scope, artifact_blobs=blobs, ledger=ledger,
    )


@pytest.fixture(scope="module")
def app(tmp_path_factory: pytest.TempPathFactory) -> FastAPI:
    """A real application, so the contract is generated and never transcribed."""
    database = tmp_path_factory.mktemp("contract") / "drift.db"
    engine = create_persistence_engine(sqlite_url(database))
    pdp = PolicyDecisionPoint.load(REPO)
    candidate_history, campaign_history = _factory_history_wiring(
        tmp_path_factory.mktemp("factory-history-var"),
    )
    return create_app(
        engine, pdp, workflow_wiring=_workflow_wiring(pdp),
        extensions=_CommandExtensions(
            operations_wiring=_operations_wiring(pdp), operations_repo_root=REPO,
            factory_candidate_history=candidate_history,
            factory_campaign_history=campaign_history,
            factory_submitter=_factory_submitter_wiring(pdp),
            preview_bridge=_preview_bridge_wiring(pdp, tmp_path_factory.mktemp("preview-bridge-var")),
        ),
    )


def canonical(schema: dict[str, Any], components: dict[str, Any]) -> str:
    """Reduce a JSON-Schema fragment to the TypeScript type it implies.

    Deliberately narrow. Anything this cannot reduce raises, because a contract
    the control cannot compare is a contract it cannot protect, and reporting
    success in that case would be the failure mode the module exists to prevent.

    `components` resolves a `$ref`. Most refs (a nested model such as
    `WorkflowNodeShape`) still reduce to their own name, so a rename or a
    restructuring is still caught field by field. The one exception is a
    `$ref` to a plain string enum (e.g. `HonestState`): TypeScript `string`
    is a real supertype of every one of its members, and `DimensionReading.
    state` deliberately declares `string` rather than restating the enum's
    members as a second, driftable copy of that vocabulary - the identical
    choice already made for `lifecycle_state`, which stays a plain `str` on
    the backend for the same reason. Any other `$ref` (an object schema)
    still returns its own name unchanged.
    """
    if "$ref" in schema:
        name = str(schema["$ref"]).rsplit("/", 1)[-1]
        target = components.get(name, {})
        if target.get("type") == "string" and "enum" in target:
            return "string"
        return name
    if "anyOf" in schema:
        options = [option for option in schema["anyOf"] if option.get("type") != "null"]
        nullable = len(options) != len(schema["anyOf"])
        if len(options) != 1:
            raise AssertionError(f"unsupported union in contract schema: {schema}")
        return canonical(options[0], components) + ("|null" if nullable else "")
    kind = schema.get("type")
    if kind == "array":
        return canonical(schema["items"], components) + "[]"
    if kind == "string":
        return "string"
    if kind in {"integer", "number"}:
        return "number"
    if kind == "boolean":
        return "boolean"
    if (
        kind == "object"
        and "properties" not in schema
        and schema.get("additionalProperties", True) is True
    ):
        # A field the backend declares as deliberately opaque - C-19's job
        # payload is the only one - reduces to an open record. Narrow on
        # purpose: an object that constrains its `properties` or its
        # `additionalProperties` is a real structure whose fields must be
        # compared, so it still falls through to the refusal below rather than
        # being flattened into something this control cannot protect.
        #
        # F-0044. The predecessor asked whether the KEY `additionalProperties`
        # was present, which conflated "the key exists" with "the key
        # constrains". `additionalProperties: true` is the explicit spelling of
        # *unconstrained* - exactly the case this branch exists to accept.
        # Pydantic 2.8 rendered `dict[str, object]` as `{type: object}` and
        # Pydantic 2.13 renders the identical declaration as
        # `{type: object, additionalProperties: true}`, so the control began
        # refusing a contract that had not changed. The backend field
        # (`contracts.py: payload: dict[str, object]`) and the frontend types
        # are both untouched since `975b1df`; only the serialiser's spelling
        # moved.
        #
        # STRENGTH IS UNCHANGED for every real constraint: `false` (a closed
        # object) and a schema-valued `additionalProperties` both still fall
        # through to the refusal, as does any object declaring `properties`.
        return "Record<string,unknown>"
    raise AssertionError(f"unsupported contract schema fragment: {schema}")


def surface_contract_names() -> frozenset[str]:
    """The models `surfaces.command` declares, so framework schemas are excluded.

    FastAPI publishes `HTTPValidationError` and `ValidationError` of its own.
    They are the framework's contract, not this surface's, and the frontend does
    not declare them.

    Spans `contracts.py` and `workflow_contracts.py` - the latter split out
    in Package 6 purely for `max_public_symbols_per_module`, not because its
    shapes belong to a different surface - plus `surfaces.operations.contracts`
    (`ARK-REQ-0396`, D-028): `/snapshot`'s `response_model` is
    `OperationsSnapshot`, owned by `surfaces.operations` and composed
    unmodified rather than restated here, so its shapes are real transport
    this surface publishes even though `surfaces.command` does not declare
    the class.
    """
    modules = (contracts, workflow_contracts, operations_contracts, factory_history, factory)
    return frozenset(
        name
        for module in modules
        for name, value in vars(module).items()
        if isinstance(value, type) and issubclass(value, BaseModel)
        and value.__module__ == module.__name__
    )


def backend_shapes(app: FastAPI) -> dict[str, dict[str, str]]:
    """Every schema this surface declares, plus the refusal envelope.

    Read from the live OpenAPI document, so the comparison is against what the
    application actually publishes. `ErrorResponse` is not a declared response
    model - it is dumped into an `HTTPException` detail - so it comes from the
    Pydantic model the refusal path actually serialises.
    """
    published = dict(app.openapi()["components"]["schemas"])
    declared = surface_contract_names()
    schemas = {name: published[name] for name in published if name in declared}
    schemas["ErrorResponse"] = ErrorResponse.model_json_schema()
    return {
        name: {
            field: canonical(fragment, published)
            for field, fragment in schema.get("properties", {}).items()
        }
        for name, schema in schemas.items()
    }


class TestTransportTypesMatchTheBackend:
    def test_every_declared_interface_names_a_real_backend_schema(
        self, app: FastAPI
    ) -> None:
        unknown = set(interfaces_of(CONTRACTS_TS)) - set(backend_shapes(app))
        assert unknown == set(), (
            f"the frontend declares transport types the backend does not publish: "
            f"{sorted(unknown)}. A removed or renamed schema must not survive here."
        )

    def test_field_names_and_types_agree_field_by_field(self, app: FastAPI) -> None:
        """The control: a rename or a type change on either side fails here."""
        expected = backend_shapes(app)
        for name, declared in interfaces_of(CONTRACTS_TS).items():
            assert declared == expected[name], (
                f"{name} has drifted. backend={expected[name]} frontend={declared}"
            )

    def test_the_slice_covers_every_shape_it_exchanges(self, app: FastAPI) -> None:
        """Nothing the UI actually sends or receives may go undeclared."""
        declared = set(interfaces_of(CONTRACTS_TS))
        exchanged = {
            "CreateProjectRequest",
            "CreateRevisionRequest",
            "TransitionRequest",
            "ProjectResponse",
            "ProjectDetailResponse",
            "ProjectListResponse",
            "RevisionResponse",
            "HealthResponse",
            "LifecycleMachineResponse",
            "ErrorResponse",
            "WorkflowNodeShape",
            "WorkflowEdgeShape",
            "PublishWorkflowRevisionRequest",
            "WorkflowRevisionResponse",
            "WorkflowRevisionDetailResponse",
            "WorkflowRevisionListResponse",
            "StartExecutionRequest",
            "ApproveExecutionRequest",
            "WorkflowNodeExecutionResponse",
            "WorkflowExecutionDetailResponse",
            "DimensionReading",
            "RuntimeSnapshot",
            "HardwareSnapshot",
            "StorageSnapshot",
            "OperationsSnapshot",
            "_FactoryGoalRequest",
            "_FactoryIntakeResponse",
            "_UnresolvedQuestionShape",
            "JobReferenceResponse",
            "_JobCheckpointResponse",
        }
        assert exchanged <= declared

    def test_a_renamed_backend_field_would_be_detected(self, app: FastAPI) -> None:
        """NEGATIVE CONTROL: prove the comparison is not vacuous.

        Rename a field in a copy of the derived truth and require the same
        comparison to reject it. Without this, a control that silently compared
        two empty dictionaries would pass forever.
        """
        expected = backend_shapes(app)
        mutated = dict(expected["ProjectResponse"])
        mutated["state"] = mutated.pop("lifecycle_state")
        assert mutated != interfaces_of(CONTRACTS_TS)["ProjectResponse"]

    def test_a_changed_backend_type_would_be_detected(self, app: FastAPI) -> None:
        """NEGATIVE CONTROL: nullability is part of the contract, not a detail."""
        expected = dict(backend_shapes(app)["RevisionResponse"])
        expected["provenance_ref"] = "string"
        assert expected != interfaces_of(CONTRACTS_TS)["RevisionResponse"]

    def test_a_ref_to_a_string_enum_reduces_to_string(self, app: FastAPI) -> None:
        """REGRESSION (root cause of the `DimensionReading.state` false-drift
        failure this control raised before `canonical()` learned to resolve a
        `$ref`). `HonestState` is a real `str` enum on the backend, so a naive
        `$ref` reduction returned the literal ref name `'HonestState'` and
        could never equal the frontend's deliberate `string` declaration -
        the exact choice already made for `lifecycle_state` above."""
        components = dict(app.openapi()["components"]["schemas"])
        assert "HonestState" in components, "fixture drifted: HonestState no longer published"
        assert canonical({"$ref": "#/components/schemas/HonestState"}, components) == "string"

    def test_a_ref_to_a_real_object_is_not_reduced_to_string(self, app: FastAPI) -> None:
        """NEGATIVE CONTROL: the string-enum exception above must stay narrow.

        A `$ref` to a real nested model (not a string enum) must still reduce
        to its own name, or a renamed/restructured nested type would silently
        compare equal to any other object and this control would stop
        catching the exact drift it exists for.
        """
        components = dict(app.openapi()["components"]["schemas"])
        assert "WorkflowNodeShape" in components, "fixture drifted: WorkflowNodeShape not published"
        assert (
            canonical({"$ref": "#/components/schemas/WorkflowNodeShape"}, components)
            == "WorkflowNodeShape"
        )


class TestRoutesMatchTheBackend:
    def declared_routes(self) -> set[tuple[str, str]]:
        found = {
            (match.group("method"), match.group("path"))
            for match in _ENDPOINT.finditer(strip_comments(read(CLIENT_TS)))
        }
        assert found, "the client declares no endpoint table to compare"
        return found

    def test_every_route_the_client_calls_exists_on_the_backend(
        self, app: FastAPI
    ) -> None:
        published = {
            (method.upper(), path)
            for path, operations in app.openapi()["paths"].items()
            for method in operations
        }
        missing = self.declared_routes() - published
        assert missing == set(), (
            f"the frontend calls routes the backend does not serve: {sorted(missing)}"
        )

    def audiences(self, app: FastAPI) -> dict[tuple[str, str], set[str]]:
        """Each published route mapped to the audience tags it declares."""
        return {
            (method.upper(), path): set(operation.get("tags", ()))
            for path, operations in app.openapi()["paths"].items()
            for method, operation in operations.items()
        }

    def test_every_route_declares_exactly_one_known_audience(
        self, app: FastAPI
    ) -> None:
        """FAILS CLOSED on a route nobody classified.

        Replaces `test_the_client_covers_every_route_the_backend_serves`, whose
        premise — every backend route is also a browser-slice route — was true
        for the Phase 5 vertical slice and expired when Package 4 added routes
        for `ARK-REQ-0027`, a requirement owned by `execution.durable` with
        `arch, integ` evidence and no `e2e`. Proven stale before replacement:
        the old assertion failed on exactly the two new routes and on nothing
        else, while every Phase 5 slice route remained covered (F-0037).

        The audience is not a list in this test. It is declared on the router
        and read back off the live document, so a route added later with no tag,
        two tags, or a tag nobody declared fails here instead of choosing its
        own exemption.
        """
        declared = self.audiences(app)
        assert declared, "no route published; this control would be vacuous"
        for route, tags in declared.items():
            known = tags & ROUTE_AUDIENCES
            assert len(known) == 1, (
                f"{route} declares audiences {sorted(tags)}; exactly one of "
                f"{sorted(ROUTE_AUDIENCES)} is required"
            )

    def test_the_client_covers_every_browser_slice_route(
        self, app: FastAPI
    ) -> None:
        """The surviving half of the old control, and still the real one.

        Within the slice an unused route is a gap, not slack. This is what the
        replaced assertion was actually protecting, now stated over the routes
        that genuinely belong to the browser.
        """
        slice_routes = {
            route for route, tags in self.audiences(app).items()
            if BROWSER_SLICE in tags
        }
        assert slice_routes, "no browser-slice route found; control is vacuous"
        assert slice_routes - self.declared_routes() == set()

    def test_the_client_calls_no_backend_only_route(self, app: FastAPI) -> None:
        """STRICTLY STRONGER than what was replaced.

        The old control could not express this at all. A frontend reaching into
        a route declared backend-only is drift in the opposite direction, and it
        would have passed the coverage assertion by making the sets match.
        """
        backend_only = {
            route for route, tags in self.audiences(app).items()
            if BACKEND_ONLY in tags
        }
        assert backend_only, "no backend-only route found; control is vacuous"
        assert backend_only & self.declared_routes() == set(), (
            "the browser client calls a route declared backend-only"
        )

    def test_a_renamed_route_would_be_detected(self, app: FastAPI) -> None:
        """NEGATIVE CONTROL: the path comparison is exact, not a prefix match."""
        published = {
            (method.upper(), path)
            for path, operations in app.openapi()["paths"].items()
            for method in operations
        }
        assert ("GET", "/api/project-registry") not in published
        assert ("GET", "/api/project-registry") not in self.declared_routes()
