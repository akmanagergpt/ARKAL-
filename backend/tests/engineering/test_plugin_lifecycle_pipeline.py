"""C-30 plugin lifecycle pipeline (ARK-REQ-0164, ARK-REQ-0165).

Phase 21 Package 1. Drives the real, pre-existing `PluginLifecycle` state
machine (Phase 3) against the real, live `OperationClassVocabulary` (Phase 4)
- not a fixture standing in for either. Proves the "unmappable permission
blocks at PERMISSIONS_DECLARED" invariant `STATE_MACHINES.md` §6 declares,
and that this module introduces no second copy of either authority.
"""

from __future__ import annotations

import pathlib
from typing import Final

import pytest

from arkali.control.policy.operation_class import OperationClassVocabulary
from arkali.engineering.plugin.lifecycle_pipeline import (
    APPROVED,
    PERMISSIONS_DECLARED,
    admit_plugin,
)
from arkali.engineering.plugin.manifest import PluginManifest
from arkali.kernel.contracts.state_machine_errors import GuardRejected

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def vocabulary() -> OperationClassVocabulary:
    return OperationClassVocabulary.load(REPO)


def _manifest(**overrides: object) -> PluginManifest:
    fields: dict[str, object] = {
        "plugin_id": "acme.example-plugin",
        "name": "Example Plugin",
        "version": "1.0.0",
        "declared_permissions": ("READ_FILE", "WRITE_WORKSPACE_FILE"),
    }
    fields.update(overrides)
    return PluginManifest(**fields)  # type: ignore[arg-type]


class TestAllPermissionsMappableReachesApproved:
    def test_reaches_approved(self, vocabulary: OperationClassVocabulary) -> None:
        outcome = admit_plugin(_manifest(), vocabulary)
        assert outcome.state == APPROVED
        assert outcome.is_approved is True
        assert outcome.unmappable_permissions == ()

    def test_zero_declared_permissions_also_reaches_approved(
        self, vocabulary: OperationClassVocabulary
    ) -> None:
        outcome = admit_plugin(_manifest(declared_permissions=()), vocabulary)
        assert outcome.state == APPROVED

    def test_every_real_canonical_class_individually_is_admissible(
        self, vocabulary: OperationClassVocabulary
    ) -> None:
        """Not a hand-picked subset — every class the live vocabulary
        actually declares, read at call time."""
        for name in vocabulary.names():
            outcome = admit_plugin(
                _manifest(declared_permissions=(name,)), vocabulary
            )
            assert outcome.state == APPROVED, name

    def test_outcome_carries_the_manifest_identity_and_ref(
        self, vocabulary: OperationClassVocabulary
    ) -> None:
        manifest = _manifest()
        outcome = admit_plugin(manifest, vocabulary)
        assert outcome.plugin_id == manifest.plugin_id
        assert outcome.manifest_ref == manifest.manifest_ref


class TestUnmappablePermissionStopsAtPermissionsDeclared:
    def test_state_stops_short_of_approved(
        self, vocabulary: OperationClassVocabulary
    ) -> None:
        outcome = admit_plugin(
            _manifest(declared_permissions=("READ_FILE", "TELEPORT_USER")),
            vocabulary,
        )
        assert outcome.state == PERMISSIONS_DECLARED
        assert outcome.is_approved is False

    def test_unmappable_permissions_are_named_and_sorted(
        self, vocabulary: OperationClassVocabulary
    ) -> None:
        outcome = admit_plugin(
            _manifest(declared_permissions=("ZAP", "READ_FILE", "ALPHA")),
            vocabulary,
        )
        assert outcome.unmappable_permissions == ("ALPHA", "ZAP")

    def test_does_not_raise(self, vocabulary: OperationClassVocabulary) -> None:
        """An unmappable permission is a named outcome, not an exception —
        ARK-REQ-0164's "cannot crash core" begins at admission time."""
        admit_plugin(_manifest(declared_permissions=("NOT_A_CLASS",)), vocabulary)

    def test_a_single_bogus_permission_among_many_real_ones_still_blocks(
        self, vocabulary: OperationClassVocabulary
    ) -> None:
        outcome = admit_plugin(
            _manifest(
                declared_permissions=("READ_FILE", "RUN_PROCESS", "BOGUS_CLASS")
            ),
            vocabulary,
        )
        assert outcome.state == PERMISSIONS_DECLARED
        assert outcome.unmappable_permissions == ("BOGUS_CLASS",)


class TestGuardIsGenuinelyConsulted:
    """The pipeline pre-filters, but the pre-existing state-machine guard is
    still the mechanism of record — a control that bypassed it would not
    prove ARK-REQ-0165."""

    def test_the_guard_itself_rejects_an_unmappable_context_directly(self) -> None:
        from arkali.engineering.plugin.plugin_lifecycle_state_machine import build

        machine = build()
        instance = machine.start("PERMISSIONS_DECLARED")
        with pytest.raises(GuardRejected):
            instance.apply(
                "APPROVED",
                context={
                    "canonical_operation_classes": ("READ_FILE",),
                    "declared_permissions": ("NOT_REAL",),
                },
            )

    def test_the_pipeline_agrees_with_the_guard_on_a_mixed_declaration(
        self, vocabulary: OperationClassVocabulary
    ) -> None:
        """The pipeline's own pre-filter and the guard it defers to must
        agree: a manifest the pipeline stops at `PERMISSIONS_DECLARED` is
        exactly one the guard itself would reject if invoked directly."""
        from arkali.engineering.plugin.plugin_lifecycle_state_machine import (
            build,
            permission_mapping_guard,
        )

        declared = ("READ_FILE", "BOGUS")
        outcome = admit_plugin(_manifest(declared_permissions=declared), vocabulary)
        assert outcome.state == PERMISSIONS_DECLARED

        guard_context = {
            "canonical_operation_classes": vocabulary.names(),
            "declared_permissions": declared,
        }
        assert permission_mapping_guard(guard_context) is False
        machine = build()
        instance = machine.start("PERMISSIONS_DECLARED")
        with pytest.raises(GuardRejected):
            instance.apply("APPROVED", context=guard_context)


class TestNoSecondAuthorityIsIntroduced:
    def test_module_declares_no_operation_class_literal(self) -> None:
        """`engineering.plugin` must not hard-code any of the fourteen
        canonical class names — F-0013's shadow-model defect."""
        import inspect

        import arkali.engineering.plugin.lifecycle_pipeline as pipeline

        source = inspect.getsource(pipeline)
        for name in (
            "READ_FILE", "WRITE_WORKSPACE_FILE", "WRITE_STABLE_FILE",
            "ROLLBACK_STABLE", "RUN_PROCESS", "APPLY_MIGRATION",
        ):
            assert name not in source, name

    def test_state_machines_document_still_declares_exactly_twelve_machines(
        self,
    ) -> None:
        from arkali.control.architecture.state_machine_spec import (
            StateMachineInventory,
        )

        inventory = StateMachineInventory.load(REPO)
        assert len(inventory) == 12
