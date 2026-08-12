"""Canonical Product Plane and Semantic Assembly vocabularies for C-25.

The Master Specification owns both lists.  Phase 12 consumers load them at
call time instead of copying the Product Plane components or the eight assembly
checks into shipping source.  Missing, malformed, duplicate and vacuous
declarations fail closed.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

from arkali.engineering.candidate.errors import (
    UnknownAssemblyCheckError,
    UnknownProductComponentError,
)
from arkali.kernel.contracts.error_base import AuthoritativeSourceError

MASTER_SPEC_RELPATH: Final[str] = "docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md"

_PRODUCT_SECTION: Final[re.Pattern[str]] = re.compile(
    r"^### Product Plane\s*$\n(?P<body>.*?)(?=^###?\s|\Z)", re.M | re.S
)
_ASSEMBLY_SECTION: Final[re.Pattern[str]] = re.compile(
    r"^## Semantic Candidate Assembly\s*$\n(?P<body>.*?)(?=^##\s|\Z)", re.M | re.S
)
_PRODUCT_SENTENCE: Final[re.Pattern[str]] = re.compile(r"^([^\n.]+)\.", re.M)
_CHECK_SENTENCE: Final[re.Pattern[str]] = re.compile(
    r"Candidate assembly validates\s+([^\n.]+)\.", re.I
)
_MINIMUM_ENTRIES: Final[int] = 2


def _slug(value: str) -> str:
    return "_to_".join(
        "_".join(part for part in re.split(r"\W+", side.lower()) if part)
        for side in value.split("↔")
    )


def _comma_list(value: str) -> tuple[str, ...]:
    # The canonical assembly sentence uses prose-list punctuation for its last
    # member (", and dependencies↔locks"); Product Plane currently does not.
    # Normalise that conjunction without treating an ``and`` inside a governed
    # name as a separator.
    value = re.sub(r",?\s+and\s+(?=[^,\n]+↔)", ", ", value)
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _declared(
    section: re.Match[str], pattern: re.Pattern[str], what: str, source: str
) -> tuple[str, ...]:
    match = pattern.search(section.group("body"))
    if match is None:
        raise AuthoritativeSourceError(
            f"the canonical {what} declaration is absent", source=source
        )
    entries = _comma_list(match.group(1))
    if len(entries) < _MINIMUM_ENTRIES:
        raise AuthoritativeSourceError(
            f"the canonical {what} has too few entries to be non-vacuous",
            source=source,
        )
    if len(set(entries)) != len(entries):
        raise AuthoritativeSourceError(
            f"the canonical {what} contains duplicate entries", source=source
        )
    return entries


class AssemblyVocabulary:
    """The two governed C-25 vocabularies. Construct with :meth:`load`."""

    def __init__(
        self, products: tuple[str, ...], checks: tuple[str, ...], source: str
    ) -> None:
        self._products = products
        self._checks = checks
        self.source = source

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> AssemblyVocabulary:
        path = repo_root / MASTER_SPEC_RELPATH
        if not path.is_file():
            raise AuthoritativeSourceError("master specification not found", source=str(path))
        body = path.read_text(encoding="utf-8")
        product = _PRODUCT_SECTION.search(body)
        assembly = _ASSEMBLY_SECTION.search(body)
        if product is None or assembly is None:
            missing = "Product Plane" if product is None else "Semantic Candidate Assembly"
            raise AuthoritativeSourceError(
                f"canonical {missing} section not found", source=str(path)
            )
        products = _declared(product, _PRODUCT_SENTENCE, "Product Plane", str(path))
        checks = _declared(assembly, _CHECK_SENTENCE, "assembly check set", str(path))
        if any("↔" not in check for check in checks):
            raise AuthoritativeSourceError(
                "every semantic assembly check must declare a consistency pair",
                source=str(path),
            )
        return cls(products, checks, str(path))

    def products(self) -> tuple[str, ...]:
        return self._products

    def checks(self) -> tuple[str, ...]:
        return self._checks

    def product_ids(self) -> tuple[str, ...]:
        return tuple(_slug(item) for item in self._products)

    def check_ids(self) -> tuple[str, ...]:
        return tuple(_slug(item) for item in self._checks)

    def require_product(self, value: str) -> str:
        identifier = _slug(value)
        if identifier not in self.product_ids():
            raise UnknownProductComponentError(
                f"{value!r} is not a canonical Product Plane component",
                source=self.source,
            )
        return identifier

    def require_check(self, value: str) -> str:
        identifier = _slug(value)
        if identifier not in self.check_ids():
            raise UnknownAssemblyCheckError(
                f"{value!r} is not a canonical semantic assembly check",
                source=self.source,
            )
        return identifier
