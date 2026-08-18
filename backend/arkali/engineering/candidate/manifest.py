"""C-25 candidate manifest: immutable references to one isolated workspace result."""

from __future__ import annotations

import json
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from arkali.engineering.candidate.assembly_vocabulary import AssemblyVocabulary
from arkali.engineering.candidate.content_identity import address_of, is_address
from arkali.engineering.candidate.errors import InvalidCandidateManifestError

MANIFEST_VERSION: Final[str] = "1.0.0"
Declared = Annotated[str, Field(min_length=1)]


class CandidateComponent(BaseModel):
    """One canonical Product Plane component and its immutable artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    component: Declared
    artifact_ref: Declared


class CandidateManifest(BaseModel):
    """The STRICT C-25 manifest produced from one ephemeral workspace.

    It deliberately records no verification, acceptance, or promotion verdict;
    those belong to later stages and authorities.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    manifest_version: str = MANIFEST_VERSION
    candidate_id: Declared
    workspace_id: Declared
    task_id: Declared
    agent_id: Declared
    snapshot_ref: Declared
    components: tuple[CandidateComponent, ...]

    @model_validator(mode="after")
    def _canonical_addresses_and_unique_components(self) -> CandidateManifest:
        if self.manifest_version.split(".")[0] != MANIFEST_VERSION.split(".")[0]:
            raise InvalidCandidateManifestError(
                f"manifest major version {self.manifest_version!r} is not readable"
            )
        references = (self.snapshot_ref, *(item.artifact_ref for item in self.components))
        if any(not is_address(reference) for reference in references):
            raise InvalidCandidateManifestError(
                "snapshot and component references must be canonical artifact addresses"
            )
        names = tuple(item.component for item in self.components)
        if len(set(names)) != len(names):
            raise InvalidCandidateManifestError("a component may appear only once")
        if not names:
            raise InvalidCandidateManifestError("a candidate manifest cannot be empty")
        return self

    @classmethod
    def assembled(
        cls,
        vocabulary: AssemblyVocabulary,
        **values: object,
    ) -> CandidateManifest:
        """Construct only after resolving every component against the authority."""
        manifest = cls.model_validate(values)
        canonical = tuple(
            item.model_copy(update={"component": vocabulary.require_product(item.component)})
            for item in manifest.components
        )
        return manifest.model_copy(update={"components": canonical})

    def rendering(self) -> bytes:
        """Stable bytes suitable for registration as the C-25 ART artifact."""
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @property
    def manifest_ref(self) -> str:
        return address_of(self.rendering())
