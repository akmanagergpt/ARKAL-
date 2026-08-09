"""Provenance evidence (`prov`) and graph readiness for Phase 6.

Phase 6 Package 3, second half. The register's Verified-by column asks for
`prov` on ARK-REQ-0004, ARK-REQ-0057 and ARK-REQ-0349, and `REQUIREMENT_REGISTER.md`
defines `prov` as *provenance* evidence - not prose. What counts as provenance
is fixed by `VDC section Provenance`: "Critical generated/release artifacts
record hash, producer/task, provider/model, spec version, context hash, parents,
normalization, tests and evidence", and by `MS section Artifact Fabric`, which
adds timestamps. This module records those items against real bytes through the
real store and then proves they are still verifiable after the database is
closed and reopened.

NO FABRICATED RELEASE. ARK-REQ-0349 names "critical generated/release
artifacts". The subject here is a Phase 6 test artifact - real bytes, real
registration, real provenance. Release manifests, SBOM and signing are C-31 at
Phase 26 and are neither implemented nor simulated.

GRAPH READINESS IS NOT A GRAPH. `TestGraphReadiness` asserts only the
storage-level properties `VERIFICATION_ARCHITECTURE.md` section 2.2 rules 1-3
name, so Phase 13 remains possible. It builds no graph, computes no coverage and
issues no verdict; that is C-16 and the Acceptance Engine.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from arkali.evidence.artifact import content_address
from arkali.evidence.artifact.errors import UnknownArtifact
from arkali.evidence.artifact.records import (
    ArtifactParentEdge,
    ArtifactProvenanceRecord,
    ArtifactRecord,
)
from arkali.evidence.audit.chain import EvidenceInput
from arkali.evidence.audit.records import AuditRecord
from tests.evidence.plane_harness import (
    Reopener,
    critical_provenance,
    phase_requirements,
    register_ids,
)
from tests.evidence.plane_harness import (  # noqa: F401 - fixtures by import
    blob_root,
    database_path,
    pdp,
    pep,
    plane,
)

PRODUCER = "tests/evidence/test_evidence_plane_provenance.py"


class TestProvenanceEvidence:
    """`prov` for ARK-REQ-0004, ARK-REQ-0057 and ARK-REQ-0349."""

    def test_every_canonical_provenance_item_is_recorded_and_bound(
        self, plane: Reopener
    ) -> None:
        source = b"def phase6():\n    return 'generated artifact'\n"
        derived = b"def phase6():\n    return 'generated artifact, normalised'\n"

        with plane.session() as writing:
            parent = writing.artifacts.register(
                source, critical_provenance(task_id="ARK-TASK-P6-P3-SOURCE")
            )
            child = writing.artifacts.register(
                derived, critical_provenance(parents=(parent,))
            )

        with plane.session() as reading:
            record = reading.artifacts.require(child)
            provenance = reading.artifacts.provenance_of(child)
            assert provenance is not None

            # hash - and it is the hash of these exact bytes, not a stored claim
            assert record.artifact_id == content_address.address_of(derived)
            algorithm, digest = content_address.parse(record.artifact_id)
            assert (record.hash_algorithm, record.digest) == (algorithm, digest)
            # producer/task, provider/model, spec version, context hash
            assert provenance.producer_agent == "arkali.phase6.package3"
            assert provenance.task_id == "ARK-TASK-P6-P3"
            assert provenance.provider_model == "none/deterministic"
            assert provenance.specification_version == "MS-2.0/C-14-1.0.0"
            assert provenance.context_hash == "sha256-of-the-compiled-context"
            # parents, normalization, tests, evidence
            assert reading.artifacts.parents_of(child) == (parent,)
            assert record.normalization == "utf-8/lf"
            assert provenance.tests and provenance.evidence
            # timestamps
            assert record.created_at is not None
            assert provenance.recorded_at is not None

            # Bound to the identity: the provenance row is keyed by the address,
            # so it cannot be re-pointed at other bytes.
            assert provenance.artifact_id == record.artifact_id

    def test_provenance_remains_verifiable_against_the_bytes_after_reopen(
        self, plane: Reopener
    ) -> None:
        """Recording is not enough; ARK-REQ-0349 needs it to stay checkable."""
        payload = b"critical generated artifact for phase 6"
        with plane.session() as writing:
            address = writing.artifacts.register(payload, critical_provenance())

        with plane.session() as reading:
            provenance = reading.artifacts.provenance_of(address)
            assert provenance is not None
            # Re-derive the identity from the stored bytes and confirm the
            # provenance still hangs off exactly that identity.
            stored_bytes = reading.artifacts.content_of(address)
            assert content_address.address_of(stored_bytes) == provenance.artifact_id

    def test_the_provenance_chain_cannot_cite_an_unregistered_parent(
        self, plane: Reopener
    ) -> None:
        """Traceability from original to derived artifact must be real."""
        absent = content_address.address_of(b"never registered")
        with plane.session() as writing:
            with pytest.raises(UnknownArtifact):
                writing.artifacts.register(
                    b"child of nothing", critical_provenance(parents=(absent,))
                )

    def test_provenance_is_evidenced_through_c15_not_asserted_in_prose(
        self, plane: Reopener
    ) -> None:
        """The `prov` obligation lands in the chain, under a real requirement."""
        requirement = "ARK-REQ-0349"
        assert requirement in phase_requirements()

        with plane.session() as writing:
            address = writing.artifacts.register(
                b"artifact whose provenance is evidenced", critical_provenance()
            )
            appended = writing.evidence.append(
                EvidenceInput(
                    requirement_id=requirement, artifact_id=address,
                    producer=PRODUCER, result="PASS", contract_id="C-14",
                    test_id="TestProvenanceEvidence::prov",
                )
            )
            record_hash = appended.record_hash

        with plane.session() as reading:
            found = reading.evidence.require(record_hash)
            assert found.requirement_id == requirement
            assert reading.artifacts.provenance_of(found.artifact_id) is not None
            assert reading.evidence.verify().verified

    def test_the_same_bytes_never_acquire_a_second_provenance_row(
        self, plane: Reopener
    ) -> None:
        """Provenance is bound to identity, so it cannot be silently replaced."""
        payload = b"registered twice"
        with plane.session() as first:
            address = first.artifacts.register(
                payload, critical_provenance(task_id="ARK-TASK-FIRST")
            )

        with plane.session() as second:
            again = second.artifacts.register(
                payload, critical_provenance(task_id="ARK-TASK-SECOND")
            )
            assert again == address

        with plane.session() as reading:
            rows = reading.session.execute(  # type: ignore[attr-defined]
                select(ArtifactProvenanceRecord).where(
                    ArtifactProvenanceRecord.artifact_id == address
                )
            ).scalars().all()
            assert len(rows) == 1
            # The first registration's provenance stands; the second did not
            # overwrite it, because an artifact record is never updated.
            assert rows[0].task_id == "ARK-TASK-FIRST"


class TestGraphReadiness:
    """Phase 6 must not write data a later evidence graph cannot use."""

    def test_every_record_carries_the_identifiers_a_graph_would_need(
        self, plane: Reopener
    ) -> None:
        requirement = phase_requirements()[0]
        with plane.session() as writing:
            address = writing.artifacts.register(b"graph node",
                                                 critical_provenance())
            writing.evidence.append(
                EvidenceInput(
                    requirement_id=requirement, artifact_id=address,
                    producer=PRODUCER, result="PASS",
                    contract_id="C-14", test_id="T3::graph",
                )
            )

        with plane.session() as reading:
            (record,) = reading.evidence.records()
            # Requirement -> Contract -> Artifact -> Test -> Evidence -> Result.
            assert record.requirement_id in register_ids()
            assert record.contract_id == "C-14"
            assert reading.artifacts.get(record.artifact_id) is not None
            assert record.test_id
            assert record.producer and record.recorded_at is not None
            assert record.result == "PASS"

    def test_no_persisted_evidence_record_is_structurally_orphaned(
        self, plane: Reopener
    ) -> None:
        """Every record resolves to a live requirement and a live artifact."""
        requirements = phase_requirements()
        with plane.session() as writing:
            for index, requirement in enumerate(requirements):
                address = writing.artifacts.register(
                    f"artifact {index}".encode(), critical_provenance()
                )
                writing.evidence.append(
                    EvidenceInput(
                        requirement_id=requirement, artifact_id=address,
                        producer=PRODUCER, result="PASS",
                    )
                )

        known = register_ids()
        with plane.session() as reading:
            records = reading.evidence.records()
            assert len(records) == len(requirements)
            for record in records:
                assert record.requirement_id in known
                assert reading.artifacts.require(record.artifact_id) is not None

    def test_supersession_preserves_both_nodes_and_the_edge(
        self, plane: Reopener
    ) -> None:
        """A `supersedes` edge, not a replacement (section 2.2 rule 1)."""
        requirement = phase_requirements()[0]
        with plane.session() as writing:
            address = writing.artifacts.register(b"two results",
                                                 critical_provenance())
            old = writing.evidence.append(
                EvidenceInput(requirement_id=requirement, artifact_id=address,
                              producer=PRODUCER, result="NOT_TESTED")
            )
            new = writing.evidence.append(
                EvidenceInput(requirement_id=requirement, artifact_id=address,
                              producer=PRODUCER, result="PASS",
                              supersedes=old.record_hash)
            )
            old_hash, new_hash = old.record_hash, new.record_hash

        with plane.session() as reading:
            hashes = [r.record_hash for r in reading.evidence.records()]
            assert old_hash in hashes and new_hash in hashes
            assert reading.evidence.require(new_hash).supersedes == old_hash

    def test_artifact_identity_is_stable_across_reopen_and_re_registration(
        self, plane: Reopener
    ) -> None:
        """A graph node needs an identity that does not move."""
        payload = b"stable identity"
        with plane.session() as first:
            address = first.artifacts.register(payload, critical_provenance())

        with plane.session() as second:
            assert second.artifacts.register(payload, critical_provenance()) == address
            rows = second.session.execute(  # type: ignore[attr-defined]
                select(ArtifactRecord).where(ArtifactRecord.artifact_id == address)
            ).scalars().all()
            assert len(rows) == 1, "re-registration must not create a second node"

    def test_the_plane_writes_only_the_tables_its_two_contracts_own(
        self, plane: Reopener
    ) -> None:
        """No third store appeared, and neither context wrote the other's rows."""
        requirement = phase_requirements()[0]
        with plane.session() as writing:
            parent = writing.artifacts.register(b"parent", critical_provenance())
            child = writing.artifacts.register(
                b"child", critical_provenance(parents=(parent,))
            )
            writing.evidence.append(
                EvidenceInput(requirement_id=requirement, artifact_id=child,
                              producer=PRODUCER, result="PASS")
            )

        with plane.session() as reading:
            session = reading.session
            counts = {
                table.__tablename__: len(
                    session.execute(select(table)).scalars().all()  # type: ignore[attr-defined]
                )
                for table in (
                    ArtifactRecord, ArtifactProvenanceRecord,
                    ArtifactParentEdge, AuditRecord,
                )
            }
        assert counts == {
            "artifact": 2, "artifact_provenance": 2,
            "artifact_parent": 1, "audit_record": 1,
        }
