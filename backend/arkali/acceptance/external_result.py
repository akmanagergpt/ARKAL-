"""ARK-REQ-0219 — never fabricate or simulate an external-provider result.

Owner: acceptance.engine (Protected Core).

THE INVARIANT IS NEGATIVE. `BP §Mandatory`: "Never fabricate or simulate an
external-provider result." Phase 9 satisfies it without producing a real
external-provider result: what must be proven is that the acceptance mechanism
cannot turn an absent, local or simulated result into an external-provider
claim.

DECLARED, NEVER INFERRED (the F-0034 precedent). A recorded run states its own
class. Nothing here reads `command`, `summary` or `evidence` prose to guess
whether something external happened, because a guess about execution is exactly
the fabrication this requirement forbids.

THE POSITIVE PATH IS CLOSED, AND IT IS CLOSED BY DERIVATION. A declared external
result is admissible only against a canonical verifiable binding. The repository
defines none: `CONTRACT_INVENTORY.md` gives the provider/model record kind `INT`,
so no provider configuration is persisted at all, and Appendix A's own predicate
for a real provider - `provider.registry.configured_real_count >= 1` - is
therefore false by construction. No request identity, response identity,
timestamp or stored verification flag is invented here to fill that gap: the
claim is refused while the gap exists, and the refusal lifts on its own when a
later canonical phase supplies both halves.

NOTHING THE ACTOR WRITES IS TRUSTED. The obligation to declare comes from the
register's Phase column for this requirement, never from the report, so a
candidate cannot escape the rule by declaring an older contract revision - the
same reason `ProtectedCoreCandidate` carries no profile field.

ONE PUBLIC ENTRY POINT. `acceptance.engine` sits at its
`max_public_surface_per_context` budget, so the vocabulary, the derivation and
the check are reached through a single name rather than nine. That is a real
reduction in what the rest of the repository may couple to, not an accounting
device, and it is the ADR-0008 answer to the budget rather than an exception.
"""

from __future__ import annotations

import enum
import pathlib
import re
from typing import TYPE_CHECKING, Final

from arkali.acceptance.governance_source import read_document
from arkali.control.registry.provider.provider_authority import ProviderAuthority

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import cycle
    from arkali.acceptance.phase_report import PhaseReport
    from arkali.control.specification.register_parser import RequirementRegister

#: Inventory kinds denoting persisted state. A record held only in memory cannot
#: carry a configured provider set across a run.
_PERSISTED_KINDS: Final[frozenset[str]] = frozenset({"DB", "DB+INT", "EVD"})
_KIND_CELL: Final[re.Pattern[str]] = re.compile(r"[A-Z]{2,4}(\+[A-Z]{2,4})?")


class ExternalProviderResultRule:
    """The ARK-REQ-0219 vocabulary, derivation and acceptance check."""

    #: The requirement enforced here. Its Phase column, not this constant,
    #: decides which reports owe a declaration.
    REQUIREMENT: Final[str] = "ARK-REQ-0219"
    #: The C-17 field a recorded run declares its class in.
    DECLARATION_FIELD: Final[str] = "external_result"
    CONTRACT_INVENTORY: Final[str] = "docs/canonical/CONTRACT_INVENTORY.md"

    class Declared(str, enum.Enum):
        """What a recorded run claims about an external provider.

        The three meanings the governing ruling requires, spelled from canonical
        vocabulary: `BP §Mandatory` supplies "external-provider result" and
        "simulate", and `ARK-REQ-0319` confines simulation to low-level testing.
        """

        #: Honest absence. Compatible with NOT_CONFIGURED, EXTERNAL_UNAVAILABLE,
        #: a refusal, or an ordinary run claiming nothing about a provider.
        NO_EXTERNAL_RESULT = "NO_EXTERNAL_RESULT"
        #: A double. Permitted where `ARK-REQ-0319` permits one, never claimable
        #: as external evidence and never able to support an external claim.
        SIMULATED_TEST_ONLY = "SIMULATED_TEST_ONLY"
        #: Claims a real external provider produced this. Admissible only
        #: against a canonical verifiable binding.
        EXTERNAL_PROVIDER_RESULT = "EXTERNAL_PROVIDER_RESULT"

        @property
        def claims_external(self) -> bool:
            return self is ExternalProviderResultRule.Declared.EXTERNAL_PROVIDER_RESULT

    # -- derivation -----------------------------------------------------------

    @staticmethod
    def phase_owes(phase_id: str, owing_phase: str) -> bool:
        """Whether a phase is at or beyond the phase that owns an obligation.

        NO SHADOW MODEL: the boundary is the register's Phase column, never a
        constant here. A phase that ran before an obligation existed is not
        retroactively in breach of it, which is what keeps every accepted
        historical report valid in its own context without touching a byte.
        """
        def rank(value: str) -> tuple[int, str]:
            digits = "".join(c for c in value if c.isdigit())
            return (int(digits) if digits else 0, value)

        return rank(phase_id) >= rank(owing_phase)

    @classmethod
    def binding(cls, repo_root: pathlib.Path) -> tuple[bool, str, str]:
        """(available, reason, source): is there a verifiable external binding?

        Derived, never asserted, and recomputed on every call so no stored flag
        can stand in for it. The Provider/Model Registry is the sole authority
        for provider identity and configuration (ARK-REQ-0052, ADR-0001), and
        `CONTRACT_INVENTORY.md` declares the kind of its record. A record that is
        not persisted holds no configured provider across a run, so Appendix A's
        `configured_real_count >= 1` cannot hold.

        NECESSARY, NOT SUFFICIENT: even with providers configured, a later
        canonical phase must still define how a request and its response are
        bound and verified. Until both exist this is False and every external
        claim is refused, rather than the missing half being invented here.
        """
        owner = ProviderAuthority.load(repo_root).owner
        text, source = read_document(repo_root, cls.CONTRACT_INVENTORY)
        kinds = cls._inventory_kinds_for(text, owner)
        if not kinds:
            return (
                False,
                f"the contract inventory declares no record owned by {owner!r}, "
                "so no provider configuration can be resolved",
                source,
            )
        persisted = sorted(k for k in kinds if k.upper() in _PERSISTED_KINDS)
        if not persisted:
            return (
                False,
                f"the record owned by {owner!r} is declared {sorted(kinds)}, which "
                "is not persisted, so configured_real_count is 0 and no external "
                "result can be bound to a configured provider",
                source,
            )
        return (
            False,
            f"the record owned by {owner!r} is persisted ({persisted}), but the "
            "canonical set still defines no verifiable request/response binding "
            "for an external-provider result; the positive path stays closed "
            "until one exists and must not be invented here",
            source,
        )

    @staticmethod
    def _inventory_kinds_for(text: str, owner: str) -> set[str]:
        """Kind cells of every inventory row whose owner cell names this context."""
        found: set[str] = set()
        for line in text.splitlines():
            if not line.startswith("|") or owner not in line:
                continue
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            if owner not in cells:
                continue
            found.update(c for c in cells if _KIND_CELL.fullmatch(c))
        return found

    # -- the acceptance check -------------------------------------------------

    @classmethod
    def undeclared_runs(cls, report: PhaseReport) -> tuple[int, ...]:
        """Runs that did not state a class explicitly.

        A default is not a declaration. Pydantic records which fields the author
        actually supplied, so a report that omits the field is distinguishable
        from one that states the non-claiming value - which is what stops a
        missing classification from ever reading as a claim.
        """
        return tuple(
            index
            for index, record in enumerate(report.tests_executed)
            if cls.DECLARATION_FIELD not in record.model_fields_set
        )

    @classmethod
    def external_runs(cls, report: PhaseReport) -> tuple[int, ...]:
        return tuple(
            index
            for index, record in enumerate(report.tests_executed)
            if getattr(record, cls.DECLARATION_FIELD).claims_external
        )

    @classmethod
    def evaluate(
        cls, repo_root: pathlib.Path, report: PhaseReport, register: RequirementRegister
    ) -> tuple[bool, str, str]:
        """(passed, summary, detail). Returns a verdict, never raises past it."""
        entry = register.get(cls.REQUIREMENT)
        if entry is None:
            return (
                False,
                f"{cls.REQUIREMENT} is absent from the requirement register",
                "the obligation cannot be located, so the check fails closed",
            )
        claimed = cls.external_runs(report)
        if claimed:
            available, reason, source = cls.binding(repo_root)
            if not available:
                return (
                    False,
                    f"{len(claimed)} recorded run(s) declare an external-provider "
                    "result that no canonical binding can substantiate",
                    f"runs={list(claimed)} reason={reason} source={source}",
                )
        owing = entry.owning_phase
        if not cls.phase_owes(report.phase_id, owing):
            return (
                True,
                f"phase {report.phase_id} predates {cls.REQUIREMENT}, which the "
                f"register assigns to phase {owing}; no declaration is owed",
                "the obligation begins when the register says it does",
            )
        missing = cls.undeclared_runs(report)
        if missing:
            return (
                False,
                "a recorded run does not declare whether it claims an "
                "external-provider result",
                f"runs={list(missing)} field={cls.DECLARATION_FIELD!r} "
                f"obligation_from_phase={owing}",
            )
        declared = sorted(
            {getattr(r, cls.DECLARATION_FIELD).value for r in report.tests_executed}
        )
        return (
            True,
            f"all {len(report.tests_executed)} recorded runs declare their "
            "external-provider class and none claims an unsubstantiated result",
            f"declared={declared} obligation_from_phase={owing}",
        )
