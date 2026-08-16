"""ARK-REQ-0331 — a UI node type without execution evidence is FAIL.

Owner: `acceptance.engine`. VDC §Workflow Studio execution identity: "For
every canonical node type ... and every control construct ... provide
execution evidence bound to the graph revision hash ... A node type present
in the UI without execution evidence is FAIL."

WHY THIS IS A STRUCTURAL TEST, NOT A NEW `acceptance.engine` MODULE.
`execution.workflow` and `surfaces.command` are both at
`max_public_symbols_per_module`'s context-wide ceiling (`max_public_surface_per_context`,
40 of 40); `acceptance.engine` is at the identical ceiling. A requirement
whose subject is "does the frontend's declared picklist agree with real
backend evidence" is exactly the shape `test_contract_drift.py` already
proves for the transport contract - a real cross-check read from both
halves' own truth, not a copy of either. This module is that same idiom,
applied to node kinds and control constructs instead of transport shapes,
and needs no new production symbol anywhere: the check is the comparison
itself, run every time this suite runs.

WHAT COUNTS AS "THE UI". `frontend/src/features/workflow/vocabulary.ts`'s
`NODE_KINDS`/`CONTROL_CONSTRUCTS` - the palette the Studio actually renders
(`NodePalette.tsx` iterates them directly; see `test_frontend_boundaries.py`'s
sibling controls for the same "declared is not used" discipline applied to
the frontend stack). Comparing against the *canonical* `GraphVocabulary`
would only prove the parser works, which Package 1's own tests already do;
this control asks the harder question - did the exact 20 items a real
browser can click actually run.

WHAT COUNTS AS "EXECUTION EVIDENCE". A real `WorkflowNodeExecutionRecord`
row, produced by a real `WorkflowExecutor` run over a real published C-20
graph - not a fixture asserting the row's shape. The single graph below
exercises every one of the 10 node kinds and 10 control constructs the
canonical vocabulary declares, pausing twice (`WAIT`, then `HUMAN APPROVAL`)
and resuming through the real `resume_after_signal`/`approve` calls Package
5 built, exactly as a browser-driven execution would.
"""

from __future__ import annotations

import pathlib
from typing import Any

from arkali.execution.workflow.graph_vocabulary import GraphVocabulary
from tests.execution.executor_harness import (  # noqa: F401 - fixtures by import
    ExecutorReopener,
    approval_gate,
    build_document,
    clock,
    database_path,
    edge,
    node,
    pdp,
    publish,
    reopen,
    vocabulary,
)
from tests.structural.typescript_reader import FRONTEND_SRC, string_array_of

VOCABULARY_TS = FRONTEND_SRC / "features" / "workflow" / "vocabulary.ts"

#: One graph, real dispatch for all 10 node kinds and all 10 control
#: constructs. Parameters are chosen so every construct's decision is
#: deterministic and reached in exactly two pauses (`WAIT`, `HUMAN APPROVAL`).
_NODES = [
    node("n-trigger", "trigger"),
    node("n-if", "logic", construct="IF", parameters={"value": True}),
    node("n-else", "logic", construct="ELSE"),
    node("n-switch", "logic", construct="SWITCH", parameters={"value": "a"}),
    node("n-loop", "logic", construct="LOOP", parameters={"max_iterations": 0}),
    node("n-parallel", "logic", construct="PARALLEL"),
    node("n-ai", "AI"),
    node("n-agent", "agent"),
    node("n-merge", "logic", construct="MERGE"),
    node("n-wait", "logic", construct="WAIT"),
    node("n-retry", "logic", construct="RETRY", parameters={"succeeded": True}),
    node("n-error", "logic", construct="ERROR HANDLER", parameters={"triggered": False}),
    node("n-approval", "logic", construct="HUMAN APPROVAL"),
    node("n-engineering", "engineering"),
    node("n-data", "data"),
    node("n-integration", "integration"),
    node("n-approval-kind", "approval"),
    node("n-release", "release"),
    node("n-notification", "notification"),
]
_EDGES = [
    edge("e-1", "n-trigger", "n-if"),
    edge("e-2", "n-if", "n-else", "true"),
    edge("e-3", "n-else", "n-switch"),
    edge("e-4", "n-switch", "n-loop", "a"),
    edge("e-5", "n-loop", "n-parallel", "exit"),
    edge("e-6", "n-parallel", "n-ai"),
    edge("e-7", "n-parallel", "n-agent"),
    edge("e-8", "n-ai", "n-merge"),
    edge("e-9", "n-agent", "n-merge"),
    edge("e-10", "n-merge", "n-wait"),
    edge("e-11", "n-wait", "n-retry"),
    edge("e-12", "n-retry", "n-error", "success"),
    edge("e-13", "n-error", "n-approval", "ok"),
    edge("e-14", "n-approval", "n-engineering"),
    edge("e-15", "n-engineering", "n-data"),
    edge("e-16", "n-data", "n-integration"),
    edge("e-17", "n-integration", "n-approval-kind"),
    edge("e-18", "n-approval-kind", "n-release"),
    edge("e-19", "n-release", "n-notification"),
]


def _run_comprehensive_execution(
    reopen: ExecutorReopener, vocabulary: GraphVocabulary
) -> list[dict[str, Any]]:
    """Publish the graph above and drive it to `SUCCEEDED`, returning every
    recorded evidence row as a plain dict (detached from the session)."""
    with reopen.session() as (executor, store, session):
        document = build_document(vocabulary, "wf-coverage", _NODES, _EDGES)
        publish(store, document)
        started = executor.start("exec-coverage", "wf-coverage")
        assert started.lifecycle_state == "WAITING_SIGNAL"

    with reopen.session() as (executor, _store, session):
        resumed = executor.resume_after_signal("exec-coverage")
        assert resumed.lifecycle_state == "WAITING_APPROVAL"

    with reopen.session() as (executor, _store, _session):
        record = executor.require("exec-coverage")
        approved = executor.approve(
            "exec-coverage",
            node_id="n-approval",
            actor="human",
            decision="APPROVED",
            approved_revision_hash=record.bound_revision_hash,
        )
        assert approved.lifecycle_state == "SUCCEEDED"
        rows = executor.evidence("exec-coverage")
        return [
            {"kind": row.kind, "control_construct": row.control_construct} for row in rows
        ]


def _missing(declared: tuple[str, ...], present: set[str]) -> frozenset[str]:
    return frozenset(declared) - present


class TestEveryUIDeclaredNodeTypeHasRealExecutionEvidence:
    def test_every_ui_declared_kind_and_construct_ran_for_real(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        evidence = _run_comprehensive_execution(reopen, vocabulary)
        present_kinds = {row["kind"] for row in evidence}
        present_constructs = {
            row["control_construct"] for row in evidence if row["control_construct"] is not None
        }

        ui_kinds = string_array_of(VOCABULARY_TS, "NODE_KINDS")
        ui_constructs = string_array_of(VOCABULARY_TS, "CONTROL_CONSTRUCTS")

        missing_kinds = _missing(ui_kinds, present_kinds)
        missing_constructs = _missing(ui_constructs, present_constructs)
        assert missing_kinds == frozenset(), (
            f"the Studio offers node kind(s) {sorted(missing_kinds)} with no "
            "real execution evidence: ARK-REQ-0331 FAIL"
        )
        assert missing_constructs == frozenset(), (
            f"the Studio offers control construct(s) {sorted(missing_constructs)} "
            "with no real execution evidence: ARK-REQ-0331 FAIL"
        )

    def test_a_ui_node_type_without_evidence_is_detected(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        """NEGATIVE CONTROL: prove the comparison is not vacuous.

        Every real evidence row for one declared kind is removed, and the
        same comparison is required to catch exactly that omission - the
        `test_contract_drift.py` anti-vacuity idiom, applied here.
        """
        evidence = _run_comprehensive_execution(reopen, vocabulary)
        present_kinds = {row["kind"] for row in evidence if row["kind"] != "notification"}
        ui_kinds = string_array_of(VOCABULARY_TS, "NODE_KINDS")

        missing_kinds = _missing(ui_kinds, present_kinds)
        assert missing_kinds == frozenset({"notification"})

    def test_the_ui_declares_exactly_the_canonical_ten_and_ten(self) -> None:
        """`vocabulary.ts` is a picklist, not an authority - see its own module
        docstring - but a picklist that fell out of step with the canonical
        counts would make the two assertions above vacuous by coincidence."""
        ui_kinds = string_array_of(VOCABULARY_TS, "NODE_KINDS")
        ui_constructs = string_array_of(VOCABULARY_TS, "CONTROL_CONSTRUCTS")
        assert len(ui_kinds) == 10
        assert len(ui_constructs) == 10
        assert len(set(ui_kinds)) == 10
        assert len(set(ui_constructs)) == 10
