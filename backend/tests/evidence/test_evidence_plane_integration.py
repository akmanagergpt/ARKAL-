"""The Evidence Plane as one composed thing: C-14 and C-15 together.

Phase 6 Package 3. Packages 1 and 2 proved each contract on its own; this module
proves they compose into the plane `MS section Evidence Plane` names
(ARK-REQ-0004) without either contract acquiring the other's authority.

The journey below is one persisted sequence, not a set of independent
assertions: register bytes through C-14, evidence them through C-15, close the
database, reopen it through a fresh engine, and re-verify both halves. The
harness (`plane_harness.py`) supplies only real infrastructure; nothing at this
tier is substituted.

WHAT THIS MODULE DOES NOT DO. It computes no coverage, derives no graph and
issues no verdict - `VERIFICATION_ARCHITECTURE.md` section 2.3 and C-16 are
Phase 13.
"""

from __future__ import annotations

import pathlib

import pytest

from arkali.evidence.artifact import content_address
from arkali.evidence.artifact.errors import ArtifactContentMismatch
from arkali.evidence.audit.chain import EvidenceInput
from arkali.evidence.audit.integrity import (
    DIGESTED_FIELDS,
    canonical_payload,
    digest_of,
)
from tests.evidence.plane_harness import (
    Reopener,
    as_utc,
    critical_provenance,
    phase_requirements,
)
from tests.evidence.plane_harness import (  # noqa: F401 - fixtures by import
    blob_root,
    database_path,
    pdp,
    pep,
    plane,
)

PRODUCER = "tests/evidence/test_evidence_plane_integration.py"


class TestEvidencePlaneJourney:
    """C-14 registers, C-15 evidences, and both survive a real reopen."""

    def test_the_full_journey_survives_reopen(self, plane: Reopener) -> None:
        payload = b"# ARKALI phase 6 evidence plane\nregistered through C-14\n"
        requirement = phase_requirements()[0]

        # 1-4: register bytes with provenance, then evidence them against a real
        # register requirement, in one committed transaction.
        with plane.session() as open_plane:
            address = open_plane.artifacts.register(payload, critical_provenance())
            record = open_plane.evidence.append(
                EvidenceInput(
                    requirement_id=requirement,
                    artifact_id=address,
                    producer=PRODUCER,
                    result="PASS",
                    contract_id="C-14",
                    test_id="TestEvidencePlaneJourney::journey",
                )
            )
            first_hash = record.record_hash

        # 5-6: the engine is disposed by the block; everything below runs on a
        # fresh engine over the same file.
        with plane.session() as reopened:
            # 7-8: the artifact resolves and its bytes still hash to its address.
            resolved = reopened.artifacts.require(address)
            assert resolved.artifact_id == address
            assert reopened.artifacts.verify(address) is True
            assert content_address.matches(
                reopened.artifacts.content_of(address), address
            )

            # 9-10: the evidence record reads back and the chain recomputes.
            stored = reopened.evidence.require(first_hash)
            verification = reopened.evidence.verify()
            assert verification.verified, verification.render()
            assert verification.length == 1

            # 11: both linkages still resolve to real things.
            assert stored.requirement_id in phase_requirements()
            assert reopened.artifacts.get(stored.artifact_id) is not None

        # 12: a later record supersedes the first.
        with plane.session() as superseding:
            second = superseding.evidence.append(
                EvidenceInput(
                    requirement_id=requirement,
                    artifact_id=address,
                    producer=PRODUCER,
                    result="PASS",
                    contract_id="C-15",
                    test_id="TestEvidencePlaneJourney::supersession",
                    supersedes=first_hash,
                )
            )
            second_hash = second.record_hash

        # 13-15: both survive, the old one is unchanged, and the chain verifies
        # after another reopen.
        with plane.session() as final:
            records = final.evidence.records()
            assert [r.record_hash for r in records] == [first_hash, second_hash]
            preserved = final.evidence.require(first_hash)
            assert preserved.contract_id == "C-14"
            assert preserved.supersedes is None
            assert final.evidence.superseded_by(first_hash) is not None
            assert final.evidence.verify().verified
            assert final.artifacts.verify(address) is True

        assert plane.opens == 4, "each stage must have used its own engine"

    def test_the_old_record_is_unchanged_by_supersession(
        self, plane: Reopener
    ) -> None:
        """Supersession appends. It rewrites no field of the record it replaces.

        "Unchanged" is asserted in the contract's own terms: the canonical
        payload the digest is taken over, plus every digested field. Comparing
        raw attributes would instead compare *driver representations* - SQLite
        hands back a naive datetime for a `DateTime(timezone=True)` column,
        which `integrity._render` normalises to UTC precisely so the digest does
        not depend on that. A test that failed on it would be testing the
        driver, not the invariant.
        """
        requirement = phase_requirements()[0]
        with plane.session() as first:
            address = first.artifacts.register(b"superseded subject",
                                               critical_provenance())
            original = first.evidence.append(
                EvidenceInput(
                    requirement_id=requirement, artifact_id=address,
                    producer=PRODUCER, result="FAIL",
                )
            )
            first_hash = original.record_hash
            payload_before = canonical_payload(original)
            fields_before = {
                name: getattr(original, name) for name in DIGESTED_FIELDS
                if name != "recorded_at"
            }
            instant_before = original.recorded_at

        with plane.session() as second:
            second.evidence.append(
                EvidenceInput(
                    requirement_id=requirement, artifact_id=address,
                    producer=PRODUCER, result="PASS", supersedes=first_hash,
                )
            )

        with plane.session() as after:
            reread = after.evidence.require(first_hash)
            assert canonical_payload(reread) == payload_before
            assert digest_of(reread) == first_hash == reread.record_hash
            for name, value in fields_before.items():
                assert getattr(reread, name) == value, f"{name} changed"
            assert as_utc(reread.recorded_at) == as_utc(instant_before)
            # The corrected outcome is a new record; the old FAIL is still there.
            assert [r.result for r in after.evidence.records()] == ["FAIL", "PASS"]

    def test_a_tampered_blob_is_caught_after_reopen_and_never_repaired(
        self, plane: Reopener, blob_root: pathlib.Path
    ) -> None:
        """The two halves do not cover for each other.

        A verifying chain says nothing about the bytes, and intact bytes say
        nothing about the chain. Both are checked independently, so corrupting
        one must not be masked by the other.
        """
        with plane.session() as first:
            address = first.artifacts.register(b"tamper me", critical_provenance())
            first.evidence.append(
                EvidenceInput(
                    requirement_id=phase_requirements()[0], artifact_id=address,
                    producer=PRODUCER, result="PASS",
                )
            )

        blob = blob_root / content_address.relative_path(address)
        blob.write_bytes(b"tampered!")

        with plane.session() as after:
            # The chain is untouched and still verifies - which is exactly why
            # it cannot be offered as proof about the bytes.
            assert after.evidence.verify().verified
            assert after.artifacts.verify(address) is False
            with pytest.raises(ArtifactContentMismatch):
                after.artifacts.content_of(address)
            # Nothing repaired the record to match the tampered bytes.
            assert after.artifacts.require(address).artifact_id == address

    def test_neither_half_can_be_reached_through_the_other(
        self, plane: Reopener
    ) -> None:
        """Composition, not collapse: two authorities remain two authorities."""
        with plane.session() as open_plane:
            assert not hasattr(open_plane.artifacts, "append")
            assert not hasattr(open_plane.evidence, "register")
            # The chain exposes no way to mint an artifact identity, and the
            # store exposes no way to write an evidence record.
            chain_surface = set(dir(open_plane.evidence))
            store_surface = set(dir(open_plane.artifacts))
            assert not {"register", "content_of", "provenance_of"} & chain_surface
            assert not {"append", "head", "records"} & store_surface
