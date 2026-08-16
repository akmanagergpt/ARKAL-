"""Deterministic C-37 blueprint derivation engine (D-025).

Owner: control.specification.

DETERMINISTIC CORE, NOT PROBABILISTIC EDGE (MS §Constitution 5). This module
contacts no AI provider and holds none of the semantic understanding a real
natural-language pipeline would eventually need — that is Probabilistic Edge
territory and explicitly out of scope for this ruling (D-025; "No external
providers or credentials"). What is built here is a real, bounded, rule-based
decomposition: sentence- and enumeration-boundary splitting, closed-vocabulary
keyword classification, and pattern-anchored constraint extraction. Every rule
is named in this docstring rather than left implicit, so the boundary between
"genuinely derived" and "would need a model" stays honest and inspectable.

NO SHADOW ARCHITECTURE AUTHORITY (`ARK-REQ-0386`). `map_architecture` reads
`AuthorityMap.concerns` at call time and returns a live concern name or None.
No `category -> owner` table is hard-coded anywhere in this module: the only
fixed data is the requirement's own text and category, matched by shared word
tokens against whatever `AUTHORITY_MAP.yaml` currently declares.
"""

from __future__ import annotations

import re
from typing import Final

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.specification.blueprint_contracts import (
    CandidateRequirement,
    ProductGoal,
    RequirementBlueprint,
    RequirementCategory,
    UnresolvedQuestion,
    UnresolvedQuestionKind,
)
from arkali.control.specification.blueprint_errors import MalformedProductGoalError

#: Enumeration-marker lines: "- x", "* x", "1. x", "1) x".
_ENUMERATION_LINE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:[-*•]|\d+[.)])\s+(?P<item>.+?)\s*$", re.M
)
#: Sentence boundary: terminal punctuation followed by whitespace.
_SENTENCE_BOUNDARY: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+")

#: Category -> closed keyword set (`ARK-REQ-0385`). A statement matching none
#: of these stays `UNCLASSIFIED` rather than defaulting to a guessed member.
_CATEGORY_KEYWORDS: Final[tuple[tuple[RequirementCategory, frozenset[str]], ...]] = (
    (RequirementCategory.SECURITY, frozenset(
        {"secure", "securely", "secured", "security", "encrypt", "encrypted",
         "auth", "authenticate", "authentication", "authorization",
         "permission", "credential", "secret"})),
    (RequirementCategory.DATA, frozenset(
        {"database", "store", "stored", "storage", "persist", "persisted",
         "schema", "record", "table", "migration"})),
    (RequirementCategory.INTEGRATION, frozenset(
        {"api", "endpoint", "integrate", "integration", "webhook",
         "external", "provider", "connector"})),
    (RequirementCategory.UI, frozenset(
        {"ui", "screen", "button", "page", "dashboard", "form", "display"})),
    (RequirementCategory.OPERATIONS, frozenset(
        {"operate", "operations", "deploy", "deployment", "monitor",
         "backup", "restore", "logging", "telemetry"})),
    (RequirementCategory.NON_FUNCTIONAL, frozenset(
        {"performance", "latency", "scalable", "scalability", "reliable",
         "reliability", "availability", "throughput"})),
)

#: Category -> extra English search anchors used only to widen the word-overlap
#: search in `map_architecture`. These are synonyms, not owners: the concern
#: (and therefore its owner) is still always resolved live from
#: `AuthorityMap.concerns`, never assigned here.
_CATEGORY_ANCHORS: Final[dict[RequirementCategory, frozenset[str]]] = {
    RequirementCategory.SECURITY: frozenset(
        {"policy", "secret", "isolation", "credential", "permission"}),
    RequirementCategory.DATA: frozenset({"project", "persistence", "record"}),
    RequirementCategory.INTEGRATION: frozenset({"provider", "registry", "model"}),
    RequirementCategory.OPERATIONS: frozenset({"telemetry", "operations"}),
    RequirementCategory.UI: frozenset({"command", "presentation"}),
    RequirementCategory.NON_FUNCTIONAL: frozenset({"availability", "health"}),
}

#: Lexical ambiguity markers (`ARK-REQ-0383`, kind AMBIGUOUS). A real signal —
#: the text either contains one of these tokens or it does not.
_AMBIGUITY_MARKERS: Final[frozenset[str]] = frozenset(
    {"tbd", "unclear", "maybe", "possibly", "unsure", "either", "or"}
)

#: Vague qualifiers that, absent any digit in the statement, make it
#: unquantified rather than merely descriptive (kind UNDERSPECIFIED).
_VAGUE_QUALIFIERS: Final[frozenset[str]] = frozenset(
    {"fast", "quick", "good", "easy", "simple", "efficient",
     "user-friendly", "scalable", "robust", "flexible", "modern", "nice"}
)

_MIN_WORDS: Final[int] = 3

#: `(subject label, subject keywords, numeric-constraint pattern)`. Two
#: requirements sharing a subject with different captured numbers are
#: CONTRADICTORY; one requirement matching is a mechanically derivable
#: acceptance criterion.
_CONSTRAINT_SUBJECTS: Final[tuple[tuple[str, frozenset[str]], ...]] = (
    ("response_time", frozenset({"response time", "latency", "respond"})),
    ("uptime", frozenset({"uptime", "availability"})),
    ("capacity", frozenset({"capacity", "concurrent users", "users"})),
)
_NUMERIC_CONSTRAINT: Final[re.Pattern[str]] = re.compile(
    r"(?:at least|at most|no more than|no less than|within|exactly)\s+"
    r"[\d,]+(?:\.\d+)?\s*[a-zA-Z%]*", re.I
)


def decompose(goal_text: str) -> tuple[str, ...]:
    """Split a goal into candidate requirement statements (`ARK-REQ-0381`).

    Enumeration lines take precedence over sentence splitting: a goal written
    as a list is decomposed by its own structure, not re-segmented by
    punctuation inside each item.
    """
    items = tuple(m.group("item").strip() for m in _ENUMERATION_LINE.finditer(goal_text))
    if items:
        return tuple(i for i in items if i)
    sentences = _SENTENCE_BOUNDARY.split(goal_text.strip())
    return tuple(s.strip() for s in sentences if s.strip())


def classify(statement: str) -> RequirementCategory:
    """Closed-vocabulary keyword classification (`ARK-REQ-0385`)."""
    words = frozenset(re.split(r"\W+", statement.lower()))
    for category, keywords in _CATEGORY_KEYWORDS:
        if words & keywords:
            return category
    return RequirementCategory.UNCLASSIFIED


def derive_acceptance_criteria(statement: str) -> tuple[str, ...]:
    """Mechanically derivable acceptance criteria (`ARK-REQ-0384`).

    Only a statement anchored to a modal ("must"/"shall"/"should") AND a
    numeric constraint pattern yields a criterion; everything else is left
    empty rather than a paraphrase invented from prose.
    """
    if not re.search(r"\b(must|shall|should)\b", statement, re.I):
        return ()
    matches = _NUMERIC_CONSTRAINT.findall(statement)
    return tuple(m.strip() for m in matches)


def _constraint_subject(statement: str) -> str | None:
    lowered = statement.lower()
    for subject, keywords in _CONSTRAINT_SUBJECTS:
        if any(k in lowered for k in keywords):
            return subject
    return None


def _is_ambiguous(statement: str) -> bool:
    words = frozenset(re.split(r"\W+", statement.lower()))
    return bool(words & _AMBIGUITY_MARKERS)


def _is_underspecified(statement: str) -> bool:
    words = re.split(r"\W+", statement.lower())
    words = [w for w in words if w]
    if len(words) < _MIN_WORDS:
        return True
    has_digit = bool(re.search(r"\d", statement))
    return bool(frozenset(words) & _VAGUE_QUALIFIERS) and not has_digit


def map_architecture(
    statement: str, category: RequirementCategory, authority_map: AuthorityMap
) -> str | None:
    """Best-matching live concern name, or None (`ARK-REQ-0386`).

    Scores every declared concern by shared word tokens against the
    requirement's own text and category; ties keep the concern declared
    first in `AUTHORITY_MAP.yaml`, so the result is a pure function of live
    canonical data plus this requirement's own words.
    """
    tokens = (
        frozenset(re.split(r"\W+", statement.lower()))
        | {category.value}
        | _CATEGORY_ANCHORS.get(category, frozenset())
    )
    best: str | None = None
    best_score = 0
    for concern in authority_map.concerns:
        concern_tokens = frozenset(concern.concern.split("_"))
        score = len(concern_tokens & tokens)
        if score > best_score:
            best, best_score = concern.concern, score
    return best


def _quality_questions(index: int, statement: str, criteria: tuple[str, ...]) -> tuple[UnresolvedQuestion, ...]:
    """AMBIGUOUS / UNDERSPECIFIED / MISSING_ACCEPTANCE_CRITERIA for one statement."""
    questions: list[UnresolvedQuestion] = []
    if _is_ambiguous(statement):
        questions.append(UnresolvedQuestion(
            subject_index=index, kind=UnresolvedQuestionKind.AMBIGUOUS,
            detail=f"statement {index} contains an unresolved alternative "
                   "or a to-be-determined marker",
        ))
    if _is_underspecified(statement):
        questions.append(UnresolvedQuestion(
            subject_index=index, kind=UnresolvedQuestionKind.UNDERSPECIFIED,
            detail=f"statement {index} is too short or uses an unquantified "
                   "qualifier with no accompanying number",
        ))
    if not criteria:
        questions.append(UnresolvedQuestion(
            subject_index=index, kind=UnresolvedQuestionKind.MISSING_ACCEPTANCE_CRITERIA,
            detail=f"statement {index} yields no mechanically derivable "
                   "acceptance criterion",
        ))
    return tuple(questions)


def _contradiction_question(
    index: int, statement: str, subjects_seen: dict[str, tuple[int, str]],
) -> UnresolvedQuestion | None:
    """A CONTRADICTORY question if `statement` disagrees with an earlier one
    on the same constraint subject; records the subject otherwise."""
    subject = _constraint_subject(statement)
    if subject is None:
        return None
    captured = tuple(_NUMERIC_CONSTRAINT.findall(statement))
    if not captured:
        return None
    if subject not in subjects_seen:
        subjects_seen[subject] = (index, captured[0])
        return None
    prior_index, prior_value = subjects_seen[subject]
    if captured[0] == prior_value:
        return None
    return UnresolvedQuestion(
        subject_index=index, kind=UnresolvedQuestionKind.CONTRADICTORY,
        detail=f"statement {index} asserts {subject!r} = {captured[0]!r}, "
               f"contradicting statement {prior_index} which asserted "
               f"{prior_value!r}",
    )


def _derive_requirement(
    index: int, statement: str, authority_map: AuthorityMap,
) -> tuple[CandidateRequirement, tuple[str, ...]]:
    """One candidate requirement plus its mechanically derived criteria."""
    category = classify(statement)
    criteria = derive_acceptance_criteria(statement)
    concern = map_architecture(statement, category, authority_map)
    requirement = CandidateRequirement(
        index=index, statement=statement, category=category,
        acceptance_criteria=criteria, owning_concern=concern,
    )
    return requirement, criteria


def derive_blueprint(
    goal_text: str,
    authority_map: AuthorityMap,
    *,
    previous: RequirementBlueprint | None = None,
) -> RequirementBlueprint:
    """The single composed entry point (`ARK-REQ-0381`…`0389`).

    Deterministic and total over well-formed input: identical `goal_text` and
    `authority_map` state always yield a byte-identical blueprint. Raises
    only on structurally empty input (`ARK-REQ-0383` governs everything
    content-level instead — it becomes `unresolved`, never a raise).
    """
    stripped = goal_text.strip()
    if not stripped:
        raise MalformedProductGoalError(
            "product goal carries no usable content", source="goal_text"
        )
    goal = ProductGoal(goal_text=stripped)
    statements = decompose(stripped)
    if not statements:
        raise MalformedProductGoalError(
            "product goal decomposed to zero candidate requirements",
            source="goal_text",
        )

    requirements: list[CandidateRequirement] = []
    unresolved: list[UnresolvedQuestion] = []
    subjects_seen: dict[str, tuple[int, str]] = {}

    for index, statement in enumerate(statements):
        requirement, criteria = _derive_requirement(index, statement, authority_map)
        requirements.append(requirement)
        unresolved.extend(_quality_questions(index, statement, criteria))
        contradiction = _contradiction_question(index, statement, subjects_seen)
        if contradiction is not None:
            unresolved.append(contradiction)

    revision = 1 if previous is None else previous.revision + 1
    previous_id = previous.blueprint_id if previous is not None else None
    return RequirementBlueprint(
        goal=goal,
        requirements=tuple(requirements),
        unresolved=tuple(unresolved),
        revision=revision,
        previous_blueprint_id=previous_id,
    )
