"""C-30 plugin lifecycle pipeline (ARK-REQ-0164, ARK-REQ-0165).

Owner: engineering.plugin. Composes, unmodified:

- `plugin_lifecycle_state_machine.build()` (Phase 3's `PluginLifecycle`,
  `STATE_MACHINES.md` §6) - the sole authority on transition legality and on
  the "an unmappable permission blocks at `PERMISSIONS_DECLARED`" invariant,
  enforced by its own pre-existing `permission_mapping_guard`.
- `control.policy.operation_class.OperationClassVocabulary` - the sole store
  of the fourteen canonical operation classes (ARK-REQ-0165: "Plugin
  permissions use the 14 canonical operation classes").

No thirteenth state machine is declared (`STATE_MACHINES.md` stays at 12) and
no second permission vocabulary is declared here. This module only drives the
existing machine through a real `PluginManifest` and records where it landed;
it decides nothing about what is or is not a valid operation class - that
remains `control.policy.operation_class`'s sole authority, read live at call
time, never copied.

NEVER RAISES FOR AN UNMAPPABLE PERMISSION. A third-party manifest declaring a
permission the canonical vocabulary does not recognise is an expected, named
outcome (the machine stops at `PERMISSIONS_DECLARED`), not a defect this
module escalates as an exception - ARK-REQ-0164's "cannot crash core" begins
here: admitting a plugin never throws merely because the plugin author asked
for more than governance allows.
"""

from __future__ import annotations

from dataclasses import dataclass

from arkali.control.policy.operation_class import OperationClassVocabulary
from arkali.engineering.plugin.manifest import PluginManifest
from arkali.engineering.plugin.plugin_lifecycle_state_machine import (
    build as build_machine,
)

DISCOVERED = "DISCOVERED"
MANIFEST_VALIDATED = "MANIFEST_VALIDATED"
PERMISSIONS_DECLARED = "PERMISSIONS_DECLARED"
APPROVED = "APPROVED"


@dataclass(frozen=True)
class PluginLifecycleOutcome:
    """Where a real `PluginLifecycle` instance landed for one manifest."""

    plugin_id: str
    manifest_ref: str
    state: str
    unmappable_permissions: tuple[str, ...]

    @property
    def is_approved(self) -> bool:
        return self.state == APPROVED


def admit_plugin(
    manifest: PluginManifest, vocabulary: OperationClassVocabulary,
) -> PluginLifecycleOutcome:
    """Drive a fresh `PluginLifecycle` instance from `DISCOVERED` as far as
    the manifest's declared permissions legally allow.

    Reaches `APPROVED` only when every declared permission maps to the live
    vocabulary; an unmappable permission stops the machine at
    `PERMISSIONS_DECLARED` (`STATE_MACHINES.md` §6's own invariant).
    """
    instance = build_machine().start(DISCOVERED)
    instance.apply(MANIFEST_VALIDATED)
    instance.apply(PERMISSIONS_DECLARED)

    canonical = set(vocabulary.names())
    unmappable = tuple(
        sorted(p for p in manifest.declared_permissions if p not in canonical)
    )
    if not unmappable:
        instance.apply(
            APPROVED,
            context={
                "canonical_operation_classes": vocabulary.names(),
                "declared_permissions": manifest.declared_permissions,
            },
        )
    return PluginLifecycleOutcome(
        plugin_id=manifest.plugin_id,
        manifest_ref=manifest.manifest_ref,
        state=instance.state,
        unmappable_permissions=unmappable,
    )


__all__ = ["admit_plugin", "PluginLifecycleOutcome"]
