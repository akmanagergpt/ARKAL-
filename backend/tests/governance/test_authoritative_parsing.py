"""Phase 2 — authoritative-source parsing and malformed-source rejection."""

from __future__ import annotations

import pathlib

import pytest
import yaml

from arkali.acceptance.governance_state import GovernanceState
from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.specification.register_parser import RequirementRegister
from arkali.kernel.contracts.errors import AuthoritativeSourceError

REPO = pathlib.Path(__file__).resolve().parents[3]


def _write_map(tmp_path: pathlib.Path, data: object) -> pathlib.Path:
    target = tmp_path / "docs" / "canonical"
    target.mkdir(parents=True, exist_ok=True)
    (target / "AUTHORITY_MAP.yaml").write_text(
        yaml.safe_dump(data), encoding="utf-8"
    )
    return tmp_path


class TestAuthorityMapParsing:
    def test_parses_live_repository(self) -> None:
        amap = AuthorityMap.load(REPO)
        assert amap.contexts, "no contexts parsed"
        assert amap.layer_ranks, "no layers parsed"
        assert len(amap.architecture_gates) == 8

    def test_missing_file_is_rejected(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(AuthoritativeSourceError):
            AuthorityMap.load(tmp_path)

    def test_malformed_yaml_is_rejected(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "docs" / "canonical"
        target.mkdir(parents=True)
        (target / "AUTHORITY_MAP.yaml").write_text("a: [1, 2\n", encoding="utf-8")
        with pytest.raises(AuthoritativeSourceError):
            AuthorityMap.load(tmp_path)

    def test_missing_required_section_is_rejected(self, tmp_path: pathlib.Path) -> None:
        _write_map(tmp_path, {"layers": [{"name": "kernel", "rank": 0}]})
        with pytest.raises(AuthoritativeSourceError) as exc:
            AuthorityMap.load(tmp_path)
        assert "missing required section" in str(exc.value)

    def test_context_referencing_unknown_layer_is_rejected(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write_map(tmp_path, {
            "layers": [{"name": "kernel", "rank": 0}],
            "contexts": {"x.y": {"layer": "nope", "protected_core": False,
                                 "module_root": "backend/arkali/x/y"}},
            "concerns": [], "architecture_budgets": {}, "architecture_gates": [],
            "human_gates": {},
        })
        with pytest.raises(AuthoritativeSourceError) as exc:
            AuthorityMap.load(tmp_path)
        assert "undeclared layers" in str(exc.value)

    def test_root_not_a_mapping_is_rejected(self, tmp_path: pathlib.Path) -> None:
        _write_map(tmp_path, ["not", "a", "mapping"])
        with pytest.raises(AuthoritativeSourceError):
            AuthorityMap.load(tmp_path)


class TestRegisterParsing:
    def test_parses_live_register(self) -> None:
        register = RequirementRegister.load(REPO)
        counts = register.classification_counts()
        assert len(register) == sum(counts.values())
        assert counts["MANDATORY"] > 0

    def test_missing_register_is_rejected(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(AuthoritativeSourceError):
            RequirementRegister.load(tmp_path)

    def test_empty_register_is_rejected(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "docs" / "canonical"
        target.mkdir(parents=True)
        (target / "REQUIREMENT_REGISTER.md").write_text("# empty", encoding="utf-8")
        with pytest.raises(AuthoritativeSourceError) as exc:
            RequirementRegister.load(tmp_path)
        assert "zero requirements" in str(exc.value)

    def test_unknown_requirement_lookup_is_rejected(self) -> None:
        register = RequirementRegister.load(REPO)
        with pytest.raises(AuthoritativeSourceError):
            register.get("ARK-REQ-9999")

    def test_every_conditional_has_an_objective_rule(self) -> None:
        register = RequirementRegister.load(REPO)
        assert register.conditional_without_rule() == ()


class TestGovernanceStateParsing:
    def test_parses_live_state(self) -> None:
        state = GovernanceState.load(REPO)
        assert state.phases, "no phase rows parsed"
        assert "HUMAN_GATE_1" in state.accepted_human_gates

    def test_missing_artifact_is_rejected(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(AuthoritativeSourceError):
            GovernanceState.load(tmp_path)

    def test_unknown_phase_is_rejected(self) -> None:
        state = GovernanceState.load(REPO)
        with pytest.raises(AuthoritativeSourceError):
            state.phase("99")

    # These three moved to the structured contract when ERR-004 replaced
    # substring matching with declared Status cells (F-0025). The new rule is
    # strictly stricter than the old one - a row that cannot be read now stops
    # acceptance instead of being skipped - so none of this relaxes the stop
    # mechanism. Exhaustive controls live in test_finding_parser.py.

    _HEADER = "| ID | Finding | Severity | Status | Owner |\n|---|---|---|---|---|\n"

    def test_table_header_is_not_read_as_a_finding(self) -> None:
        """Regression: a header cell reading 'Blocker' was counted as a finding."""
        assert GovernanceState._parse_open_findings(self._HEADER) == ()

    def test_open_high_row_is_detected(self) -> None:
        parsed = GovernanceState._parse_open_findings(
            self._HEADER + "| EXT-9 | something broken | HIGH | OPEN | owner |\n"
        )
        assert parsed == ("EXT-9",)

    def test_closed_rows_are_excluded(self) -> None:
        assert GovernanceState._parse_open_findings(
            self._HEADER + "| EXT-1 | old | HIGH | CLOSED | o |\n"
        ) == ()

    def test_a_row_with_no_declared_status_now_stops_rather_than_vanishing(
        self,
    ) -> None:
        """The F-0025 fix: unreadable is louder than open, never quieter."""
        parsed = GovernanceState._parse_open_findings(
            "| ID | Finding | Severity | Owner |\n|---|---|---|---|\n"
            "| EXT-8 | no status column | HIGH | o |\n"
        )
        assert parsed == ("EXT-8",)
