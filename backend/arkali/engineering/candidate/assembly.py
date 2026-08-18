"""C-25 semantic assembly execution and immutable report.

Each canonical consistency pair is evaluated by a boundary adapter.  Adapters
reduce their two domain-specific sides to semantic fingerprints; this context
compares those fingerprints and records the facts without issuing an
acceptance, release, or stable-product verdict.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from arkali.engineering.candidate.assembly_vocabulary import AssemblyVocabulary
from arkali.engineering.candidate.content_identity import address_of, is_address
from arkali.engineering.candidate.errors import InvalidAssemblyReportError
from arkali.engineering.candidate.manifest import CandidateManifest

ASSEMBLY_REPORT_VERSION: Final[str] = "1.0.0"
Declared = Annotated[str, Field(min_length=1)]


class AssemblyObservation(BaseModel):
    """Semantic fingerprints independently derived for one consistency pair."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    left_ref: Declared
    right_ref: Declared

    @model_validator(mode="after")
    def _content_addressed(self) -> AssemblyObservation:
        if not is_address(self.left_ref) or not is_address(self.right_ref):
            raise InvalidAssemblyReportError(
                "assembly observations must use canonical content addresses"
            )
        return self


class AssemblyCheckResult(BaseModel):
    """Recorded outcome for one canonical pair; ``consistent`` is derived."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    check: Declared
    left_ref: Declared
    right_ref: Declared
    consistent: bool

    @model_validator(mode="after")
    def _result_is_derived(self) -> AssemblyCheckResult:
        expected = self.left_ref == self.right_ref
        if self.consistent is not expected:
            raise InvalidAssemblyReportError(
                "assembly consistency must be derived from the two semantic fingerprints"
            )
        return self


class AssemblyReport(BaseModel):
    """STRICT, manifest-bound result of executing the canonical check set."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    report_version: str = ASSEMBLY_REPORT_VERSION
    candidate_id: Declared
    manifest_ref: Declared
    checks: tuple[AssemblyCheckResult, ...]
    all_consistent: bool

    @model_validator(mode="after")
    def _internally_consistent(self) -> AssemblyReport:
        if self.report_version.split(".")[0] != ASSEMBLY_REPORT_VERSION.split(".")[0]:
            raise InvalidAssemblyReportError(
                f"assembly report major version {self.report_version!r} is not readable"
            )
        if not is_address(self.manifest_ref):
            raise InvalidAssemblyReportError("manifest_ref must be a canonical address")
        names = tuple(item.check for item in self.checks)
        if not names or len(set(names)) != len(names):
            raise InvalidAssemblyReportError(
                "an assembly report needs a nonempty, unique check set"
            )
        if self.all_consistent is not all(item.consistent for item in self.checks):
            raise InvalidAssemblyReportError(
                "all_consistent must be derived from every recorded check"
            )
        return self

    def rendering(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @property
    def report_ref(self) -> str:
        return address_of(self.rendering())


CheckEvaluator = Callable[[CandidateManifest], AssemblyObservation]


class SemanticAssembler:
    """Execute exactly the check set read from the canonical specification."""

    def __init__(
        self,
        vocabulary: AssemblyVocabulary,
        evaluators: Mapping[str, CheckEvaluator],
    ) -> None:
        canonical = vocabulary.check_ids()
        resolved: dict[str, CheckEvaluator] = {}
        for name, evaluator in evaluators.items():
            identifier = vocabulary.require_check(name)
            if identifier in resolved:
                raise InvalidAssemblyReportError(
                    f"duplicate evaluator for canonical check {identifier!r}"
                )
            resolved[identifier] = evaluator
        missing = tuple(item for item in canonical if item not in resolved)
        if missing:
            raise InvalidAssemblyReportError(
                f"every canonical assembly check needs an evaluator; missing {missing!r}"
            )
        self._vocabulary = vocabulary
        self._evaluators = resolved

    def assemble(self, manifest: CandidateManifest) -> AssemblyReport:
        results: list[AssemblyCheckResult] = []
        for check in self._vocabulary.check_ids():
            try:
                observation = self._evaluators[check](manifest)
            except InvalidAssemblyReportError:
                raise
            except Exception as error:
                raise InvalidAssemblyReportError(
                    f"semantic assembly check {check!r} could not be evaluated"
                ) from error
            if not isinstance(observation, AssemblyObservation):
                raise InvalidAssemblyReportError(
                    f"semantic assembly check {check!r} returned no valid observation"
                )
            results.append(
                AssemblyCheckResult(
                    check=check,
                    left_ref=observation.left_ref,
                    right_ref=observation.right_ref,
                    consistent=observation.left_ref == observation.right_ref,
                )
            )
        outcome = tuple(results)
        return AssemblyReport(
            candidate_id=manifest.candidate_id,
            manifest_ref=manifest.manifest_ref,
            checks=outcome,
            all_consistent=all(item.consistent for item in outcome),
        )
