"""C-21 admission authority controls (Phase 8 Package 2).

Split from `test_scheduler_authority.py`, which reached **466 logical lines**
against the 400 budget when Package 2's controls landed. ADR-0008 makes
decomposition the answer to a budget rather than an exception, and the seam is a
real one rather than an arithmetic split: this module asserts what the
*admission decision* may and may not become, while its sibling asserts the
*declaration* boundaries Package 1 established. The F-0032 precedent is
`test_durable_recovery.py`, decomposed the same way for the same budget.

Every subject is DERIVED from the deployed source or the canonical documents.
"""

from __future__ import annotations

import ast

from arkali.control.isolation.isolation_contract import IsolationAuthority
from arkali.execution.scheduler.resource_admission import ResourceAdmission
from tests.structural.scheduler_reader import (
    ALLOCATION_NAMES,
    FORWARD_NAMES,
    PACKAGE,
    PROVIDER_RUNTIME_IMPORTS,
    PROVIDER_RUNTIME_NAMES,
    REPO,
    SCHEDULER,
    declared_names,
    imported,
    modules,
    read,
    string_constants,
    takes_a_policy_decision,
)


def _only_declares_a_signature(node: ast.FunctionDef) -> bool:
    """Whether a def only DECLARES a signature - a Protocol member.

    `CapabilityResolver.can_perform` names the question the scheduler is allowed
    to ask; its body is `...` and it answers nothing. Counting a declaration as
    an implementation would forbid the scheduler from depending on the canonical
    question at all, which is the opposite of what this control wants. A bare
    signature also cannot become an escape hatch: returning `None` satisfies
    neither the type checker nor any behavioural control.
    """
    body = [
        statement for statement in node.body
        if not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        )
    ]
    return all(
        isinstance(statement, ast.Pass)
        or (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and statement.value.value is Ellipsis
        )
        for statement in body
    )



class TestAdmissionDoesNotOverreach:
    """Package 1 declares. It admits nothing and queues nothing."""

    def test_no_allocation_or_execution_vocabulary_is_defined_or_called(self) -> None:
        """Admission decides; allocation hands work out. Only the first is Phase 8.

        The subject is identifiers, not prose: a refusal message may say
        "admitting" while the module allocates nothing.
        """
        for path in modules(SCHEDULER):
            for identifier in declared_names(path):
                lowered = identifier.lower()
                for name in ALLOCATION_NAMES:
                    assert name not in lowered, (
                        f"{path.name} defines or calls {identifier!r}; admission "
                        "may decide but must not hand work out"
                    )

    def test_no_forward_phase_concept_is_defined_or_called(self) -> None:
        """Queue, priority, fairness, autoscaling and friends are not Phase 8."""
        for path in modules(SCHEDULER):
            for identifier in declared_names(path):
                lowered = identifier.lower()
                for name in FORWARD_NAMES:
                    assert name not in lowered, (
                        f"{path.name} defines or calls {identifier!r}; the "
                        "canonical set does not give Phase 8 that concept"
                    )

    def test_no_provider_runtime_is_pulled_forward(self) -> None:
        """Provider EXECUTION is Phase 9. The provider worker *class* is Phase 8.

        Deliberately not a ban on the word `provider`: that is one of the seven
        canonical worker classes, and a control forbidding it would forbid the
        canonical vocabulary itself. What is forbidden is the runtime - the
        registry import, or an operation that runs one.
        """
        for path in modules(SCHEDULER):
            for module in imported(ast.parse(read(path))):
                assert not module.startswith(PROVIDER_RUNTIME_IMPORTS), (
                    f"{path.name} -> {module}; provider runtime is Phase 9"
                )
            for identifier in declared_names(path):
                lowered = identifier.lower()
                for name in PROVIDER_RUNTIME_NAMES:
                    assert name not in lowered, (
                        f"{path.name} defines or calls {identifier!r}"
                    )

    def test_the_scheduler_never_activates_or_mutates_capability_state(self) -> None:
        """Package 2 may ASK the capability authority. It may not change it.

        Activation is Phase 9B. `CapabilityGraph.activate` always refuses in the
        schema phase, but a scheduler that called it would be asserting an
        authority it does not have, so the call is forbidden outright.
        """
        forbidden = ("activate", "configured_state", "ConfiguredState")
        for path in modules(SCHEDULER):
            for identifier in declared_names(path):
                for name in forbidden:
                    assert name not in identifier, (
                        f"{path.name} names {identifier!r}; capability activation "
                        "and configured state belong to Phase 9B"
                    )



class TestAdmissionAuthorityIsNotDuplicated:
    """Package 2 asks the canonical authorities. It becomes none of them."""

    def test_no_shipping_module_outside_control_capability_answers_can_perform(
        self,
    ) -> None:
        """The substitution guard.

        The ADMITTED branch is reachable in tests only through a test-only
        resolver, because production capability is `NOT_CONFIGURED` until Phase
        9B. That double must therefore be impossible to ship: nothing under
        `backend/arkali/` may answer the capability question except the context
        that owns it.
        """
        owner = PACKAGE / "control" / "capability"
        answering = []
        for path in modules(PACKAGE):
            if owner in path.parents:
                continue
            for node in ast.walk(ast.parse(read(path))):
                if not isinstance(node, ast.FunctionDef):
                    continue
                if node.name == "can_perform" and not _only_declares_a_signature(node):
                    answering.append(path.relative_to(PACKAGE).as_posix())
        assert not answering, (
            f"these shipping modules answer the capability question: {answering}; "
            "control.capability is its sole authority"
        )
        assert any(
            "can_perform" in read(p) for p in modules(SCHEDULER)
        ), "the scheduler asks nothing of the capability authority; control vacuous"

    def test_the_scheduler_declares_no_capability_or_isolation_vocabulary(
        self,
    ) -> None:
        """No copied tier, property or configured-state table."""
        isolation = IsolationAuthority.load(REPO)
        canonical = set(isolation.properties) | set(isolation.tiers)
        for path in modules(SCHEDULER):
            leaked = sorted(string_constants(path) & canonical)
            # TRUST-0 is the actor's own declared tier in the PolicyRequest, not
            # a copy of the tier vocabulary; every other member would be.
            assert leaked in ([], ["TRUST-0"]), (
                f"{path.name} hard-codes canonical isolation vocabulary {leaked}"
            )

    def test_the_scheduler_holds_no_mutable_resource_universe(self) -> None:
        """Availability is an input per evaluation, never accumulated state."""
        subject = ResourceAdmission()
        assert not vars(subject), f"resource evaluator holds state: {vars(subject)}"
        for path in modules(SCHEDULER):
            for node in ast.walk(ast.parse(read(path))):
                if not isinstance(node, ast.AnnAssign) or not node.simple:
                    continue
                rendered = ast.unparse(node.annotation)
                if isinstance(node.target, ast.Name) and node.target.id.isupper():
                    assert not rendered.startswith(("list", "dict", "set")), (
                        f"{path.name} declares a mutable module-level "
                        f"{rendered} - a global resource pool is not Phase 8"
                    )

    def test_admission_takes_a_real_policy_decision(self) -> None:
        assert takes_a_policy_decision(SCHEDULER / "admission.py"), (
            "the admission composition must consult the PEP itself"
        )

    def test_no_admission_module_imports_durable_or_evidence(self) -> None:
        """Both were measured as forbidden or depth-breaching before Package 2."""
        for path in modules(SCHEDULER):
            for module in imported(ast.parse(read(path))):
                assert not module.startswith("arkali.evidence"), (
                    f"{path.name} -> {module}; a scheduler -> evidence production "
                    "edge measured depth 5. Evidence comes from the test tier"
                )
                assert not module.startswith("arkali.execution.durable"), (
                    f"{path.name} -> {module}"
                )


