"""The composed Phase 16 real-authority journey.

resolved C-37 blueprint -> tier selection (deterministic tool) -> real
scaffold written to a real candidate workspace -> real import/execution ->
a larger blueprint proves progression -> a simulated quota-exhaustion case
proves failover without false PASS and without losing task identity —
over REAL `AuthorityMap`, `RequirementRegister`, `WorkspaceAuthority`,
`RepairBudgetLedger` and the Phase 15 blueprint engine. No mocks of any
canonical authority; no AI provider is contacted anywhere in this journey.
"""

from __future__ import annotations

import importlib.util
import pathlib
from decimal import Decimal

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.specification.blueprint_engine import derive_blueprint
from arkali.control.specification.register_parser import RequirementRegister
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.engineering.factory.errors import UnresolvedBlueprintError
from arkali.engineering.factory.execution_routing import (
    ExecutionTier,
    TierEligibilityRequest,
    TierState,
    select_execution_tier,
)
from arkali.engineering.factory.product_generation import generate_product
from arkali.engineering.repair.contracts import (
    RepairBudget,
    RepairBudgetLedger,
    RepairConsumption,
    RepairFingerprint,
)

REPO = pathlib.Path(__file__).resolve().parents[3]

SMALL_GOAL = "The system must respond within at least 200 ms."
LARGER_GOAL = (
    "The system must respond within at least 200 ms. "
    "The system must support at most 500 users. "
    "The system must be available for at least 99 percent."
)


def _new_workspace(tmp_path: pathlib.Path, workspace_id: str):
    stable = tmp_path / "stable"
    if not stable.is_dir():
        stable.mkdir()
        (stable / "README.md").write_text("x", encoding="utf-8")
    authority = WorkspaceAuthority(tmp_path / "workspaces")
    return authority.allocate(
        workspace_id=workspace_id, task_id=f"task-{workspace_id}", agent_id="agent-1",
        stable_snapshot=stable,
    )


def test_step_1_the_real_register_and_authority_map_denominator() -> None:
    register = RequirementRegister.load(REPO)
    phase16 = {r.req_id for r in register.for_phase("16")}
    assert phase16 == {"ARK-REQ-0233", "ARK-REQ-0392", "ARK-REQ-0393"}
    authority_map = AuthorityMap.load(REPO)
    assert authority_map.concerns  # real, non-empty, live


def test_step_2_a_resolved_blueprint_selects_the_deterministic_tier() -> None:
    authority_map = AuthorityMap.load(REPO)
    blueprint = derive_blueprint(SMALL_GOAL, authority_map)
    assert blueprint.is_fully_resolved

    request = TierEligibilityRequest(task_id="job-1", deterministic_capable=True)
    selection = select_execution_tier(request)
    assert selection.selected is ExecutionTier.DETERMINISTIC_TOOL


def test_step_3_generation_writes_a_real_importable_executable_artifact(
    tmp_path: pathlib.Path,
) -> None:
    authority_map = AuthorityMap.load(REPO)
    blueprint = derive_blueprint(SMALL_GOAL, authority_map)
    workspace = _new_workspace(tmp_path, "journey-1")

    product = generate_product(blueprint, workspace)
    module_path = workspace.path_for(product.module_relpath)
    assert module_path.is_file()

    spec = importlib.util.spec_from_file_location("phase16_journey_product", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, product.functions[0].name)
    assert fn(150) is False
    assert fn(250) is True


def test_step_4_a_larger_blueprint_generates_a_measurably_harder_product(
    tmp_path: pathlib.Path,
) -> None:
    authority_map = AuthorityMap.load(REPO)
    small = derive_blueprint(SMALL_GOAL, authority_map)
    larger = derive_blueprint(LARGER_GOAL, authority_map)
    assert larger.is_fully_resolved
    workspace = _new_workspace(tmp_path, "journey-2")

    small_product = generate_product(small, workspace)
    larger_product = generate_product(larger, workspace)
    assert len(larger_product.functions) > len(small_product.functions)


def test_step_5_an_unresolved_blueprint_is_blocked_not_generated(
    tmp_path: pathlib.Path,
) -> None:
    authority_map = AuthorityMap.load(REPO)
    ambiguous = derive_blueprint("Orders must persist.", authority_map)
    assert not ambiguous.is_fully_resolved
    workspace = _new_workspace(tmp_path, "journey-3")

    try:
        generate_product(ambiguous, workspace)
        raise AssertionError("an unresolved blueprint must never generate")
    except UnresolvedBlueprintError:
        pass
    assert not (workspace.root / "generated_product" / "product.py").exists()


def test_step_6_failover_on_a_repeated_strategy_falls_through_without_false_pass() -> None:
    """Simulated chaos: the preferred (deterministic) strategy has already
    failed once for this exact fingerprint (a quota/capacity-style repeat).
    The routing decision must fail over to the next real tier — here,
    HUMAN_GOVERNANCE, since no local/cloud/knowledge authority is live — and
    must never re-select or fabricate a DETERMINISTIC_TOOL success."""
    fingerprint = RepairFingerprint(
        failure_signature="quota_exhausted", root_cause_class="provider_unavailable",
        files=("generated_product/product.py",), strategy="scaffold-v1",
        provider_model="local/deterministic", outcome="failed",
    )
    ledger = RepairBudgetLedger(
        candidate_id="journey-candidate",
        budget=RepairBudget(
            attempts=5, ai_calls=0, elapsed_seconds=300, cost=Decimal("0"),
            touched_files=5, regression_delta=0,
        ),
        consumption=RepairConsumption(attempts=1),
        fingerprints=(fingerprint,),
    )
    repeat = RepairFingerprint(
        failure_signature="quota_exhausted", root_cause_class="provider_unavailable",
        files=("generated_product/product.py",), strategy="scaffold-v1",
        provider_model="local/deterministic", outcome="pending",
    )

    request = TierEligibilityRequest(task_id="job-durable-42", deterministic_capable=True)
    selection = select_execution_tier(request, ledger=ledger, fingerprint=repeat)

    deterministic_eval = next(
        e for e in selection.evaluations if e.tier is ExecutionTier.DETERMINISTIC_TOOL
    )
    assert deterministic_eval.state is TierState.EXHAUSTED
    assert selection.selected is ExecutionTier.HUMAN_GOVERNANCE
    # Task identity survives the failover unchanged — nothing was regenerated.
    assert selection.task_id == "job-durable-42"


def test_step_7_no_external_provider_is_contacted_anywhere_in_the_journey() -> None:
    """Matches the D-023 precedent every prior phase's journey proves: this
    entire journey uses only local/deterministic authorities."""
    authority_map = AuthorityMap.load(REPO)
    blueprint = derive_blueprint(SMALL_GOAL, authority_map)
    for requirement in blueprint.requirements:
        assert requirement.owning_concern != "cloud"
    request = TierEligibilityRequest(task_id="job-audit", deterministic_capable=True)
    selection = select_execution_tier(request)
    for evaluation in selection.evaluations:
        if evaluation.tier in (
            ExecutionTier.CLOUD_PROVIDER, ExecutionTier.STRONGER_CLOUD_SPECIALIST,
        ):
            assert evaluation.state is TierState.NOT_CONFIGURED
