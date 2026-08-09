"""Content addressing is deterministic, derived and total (ARK-REQ-0057).

Tested directly rather than through the store, because the whole guarantee rests
on this module being a pure function of the bytes. A determinism claim proved
only through a database would be proving the database.
"""

from __future__ import annotations

import hashlib

import pytest

from arkali.evidence.artifact import content_address
from arkali.evidence.artifact.errors import InvalidArtifactIdentity


class TestDeterminism:
    def test_the_same_bytes_always_yield_the_same_address(self) -> None:
        payload = b"ARKALI artifact payload"
        assert content_address.address_of(payload) == content_address.address_of(payload)

    def test_the_address_is_the_real_digest_of_the_bytes(self) -> None:
        """Computed independently here, so a broken implementation cannot agree
        with itself and pass."""
        payload = b"independent check"
        expected = f"sha256:{hashlib.sha256(payload).hexdigest()}"
        assert content_address.address_of(payload) == expected

    def test_nothing_but_the_bytes_participates(self) -> None:
        """No timestamp, host fact or call order may enter the digest."""
        first = content_address.address_of(b"stable")
        for _ in range(5):
            assert content_address.address_of(b"stable") == first

    def test_the_empty_payload_has_an_address(self) -> None:
        """Totality: every byte sequence is addressable, including the empty one."""
        assert content_address.is_address(content_address.address_of(b""))


class TestSensitivity:
    @pytest.mark.parametrize(
        "mutated",
        [b"payloaD", b"payload ", b" payload", b"paylo\x00ad", b"payloa", b"payloadX"],
    )
    def test_any_byte_change_changes_the_address(self, mutated: bytes) -> None:
        """NEGATIVE CONTROL: identity must track content, not resemble it."""
        assert content_address.address_of(mutated) != content_address.address_of(b"payload")

    def test_a_single_flipped_bit_changes_the_address(self) -> None:
        original = bytes([0b0000_0001])
        flipped = bytes([0b0000_0011])
        assert content_address.address_of(original) != content_address.address_of(flipped)

    def test_matches_reports_disagreement(self) -> None:
        address = content_address.address_of(b"one")
        assert content_address.matches(b"one", address)
        assert not content_address.matches(b"two", address)


class TestCanonicalForm:
    @pytest.mark.parametrize(
        "malformed",
        [
            "",
            "deadbeef",
            "sha256:short",
            "md5:" + "0" * 64,
            "sha256:" + "0" * 63,
            "sha256:" + "0" * 65,
            "sha256:" + "A" * 64,
            " sha256:" + "0" * 64,
            "sha256:" + "0" * 64 + " ",
        ],
    )
    def test_a_non_canonical_address_is_refused(self, malformed: str) -> None:
        """Accepting a lenient spelling would file the same bytes twice."""
        with pytest.raises(InvalidArtifactIdentity):
            content_address.parse(malformed)
        assert not content_address.is_address(malformed)

    def test_parse_returns_the_algorithm_and_digest(self) -> None:
        algorithm, digest = content_address.parse(content_address.address_of(b"x"))
        assert algorithm == content_address.ALGORITHM
        assert digest == content_address.digest_of(b"x")

    def test_matches_refuses_a_malformed_address_rather_than_returning_false(self) -> None:
        """A malformed address is a typed error, not 'different content'."""
        with pytest.raises(InvalidArtifactIdentity):
            content_address.matches(b"x", "not-an-address")


class TestLayout:
    def test_the_path_is_a_pure_function_of_the_address(self) -> None:
        address = content_address.address_of(b"layout")
        assert content_address.relative_path(address) == content_address.relative_path(address)

    def test_the_path_shards_on_the_digest(self) -> None:
        address = content_address.address_of(b"layout")
        _algorithm, digest = content_address.parse(address)
        assert content_address.relative_path(address) == f"sha256/{digest[:2]}/{digest}"

    def test_different_content_never_shares_a_path(self) -> None:
        one = content_address.relative_path(content_address.address_of(b"a"))
        two = content_address.relative_path(content_address.address_of(b"b"))
        assert one != two
