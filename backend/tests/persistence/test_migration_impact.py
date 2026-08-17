"""C-03 migration impact analysis evidence (ARK-REQ-0151 step 1, ARK-REQ-0337).

The analyser is proven against synthetic revisions (both directions) and then
against the real declared chain, so the property this exists for - a real
migration carrying a destructive operation is flagged, and no real accepted
migration is falsely flagged - is checked on both a fixture and the genuine
shipping chain.
"""

from __future__ import annotations

import pathlib

import pytest

from arkali.kernel.persistence.migration_impact import (
    analyze_chain,
    analyze_file,
    analyze_revision,
)
from arkali.kernel.persistence.migrations import VERSIONS_DIR, declared_migrations

BACKEND = pathlib.Path(__file__).resolve().parents[2]


class TestAdditiveOperationsCarryNoRisk:
    def test_create_table_is_not_flagged(self) -> None:
        report = analyze_revision(
            "0100_add_widget",
            'revision = "0100_add_widget"\n'
            "def upgrade() -> None:\n"
            "    op.create_table('widget', sa.Column('id', sa.Integer()))\n",
        )
        assert report.data_loss_risk is False
        assert report.reasons == ()

    def test_add_column_is_not_flagged(self) -> None:
        report = analyze_revision(
            "0101_add_column",
            "def upgrade() -> None:\n"
            "    op.add_column('widget', sa.Column('note', sa.String()))\n",
        )
        assert report.data_loss_risk is False

    def test_a_revision_with_no_upgrade_function_carries_no_risk(self) -> None:
        report = analyze_revision("0102_empty", "x = 1\n")
        assert report.data_loss_risk is False


class TestDestructiveOperationsAreFlagged:
    def test_drop_table_is_flagged(self) -> None:
        report = analyze_revision(
            "0200_drop_widget",
            "def upgrade() -> None:\n    op.drop_table('widget')\n",
        )
        assert report.data_loss_risk is True
        assert "drop_table" in report.reasons[0]

    def test_drop_column_is_flagged(self) -> None:
        report = analyze_revision(
            "0201_drop_column",
            "def upgrade() -> None:\n    op.drop_column('widget', 'note')\n",
        )
        assert report.data_loss_risk is True
        assert "drop_column" in report.reasons[0]

    def test_raw_drop_sql_is_flagged(self) -> None:
        report = analyze_revision(
            "0202_raw_drop",
            "def upgrade() -> None:\n    op.execute('DROP TABLE widget')\n",
        )
        assert report.data_loss_risk is True

    def test_raw_truncate_sql_is_flagged(self) -> None:
        report = analyze_revision(
            "0203_raw_truncate",
            "def upgrade() -> None:\n    op.execute('TRUNCATE widget')\n",
        )
        assert report.data_loss_risk is True

    def test_multiple_reasons_are_all_recorded(self) -> None:
        report = analyze_revision(
            "0204_two_drops",
            "def upgrade() -> None:\n"
            "    op.drop_column('widget', 'a')\n"
            "    op.drop_table('gadget')\n",
        )
        assert len(report.reasons) == 2

    def test_a_destructive_downgrade_does_not_flag_the_upgrade(self) -> None:
        """Only `upgrade()` is analysed - `downgrade()` reversing a create is
        expected to drop what it made and is not this analysis's subject."""
        report = analyze_revision(
            "0205_create_only",
            "def upgrade() -> None:\n    op.create_table('widget')\n"
            "def downgrade() -> None:\n    op.drop_table('widget')\n",
        )
        assert report.data_loss_risk is False


class TestFileAndChainAnalysis:
    def test_analyze_file_reads_a_real_file(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "0300_x.py"
        path.write_text(
            "def upgrade() -> None:\n    op.drop_table('x')\n", encoding="utf-8"
        )
        report = analyze_file(path)
        assert report.revision == "0300_x"
        assert report.data_loss_risk is True

    def test_analyze_chain_orders_by_filename_and_skips_init(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "0002_b.py").write_text(
            "def upgrade() -> None:\n    pass\n", encoding="utf-8"
        )
        (tmp_path / "0001_a.py").write_text(
            "def upgrade() -> None:\n    op.drop_table('a')\n", encoding="utf-8"
        )
        reports = analyze_chain(tmp_path)
        assert [r.revision for r in reports] == ["0001_a", "0002_b"]
        assert reports[0].data_loss_risk is True
        assert reports[1].data_loss_risk is False

    def test_a_missing_directory_is_refused(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError):
            analyze_chain(tmp_path / "nowhere")


class TestTheRealShippingChainCarriesNoKnownDataLossRisk:
    """ARK-REQ-0337's property, proven against the genuine chain: every
    accepted migration through Phase 19 is additive (CONTRACT_INVENTORY.md
    marks C-03 STRICT/migration-numbered, and every consuming contract this
    chain serves is ADDITIVE or STRICT-append), so none may be flagged."""

    def test_no_real_revision_carries_a_known_data_loss_risk(self) -> None:
        reports = analyze_chain(BACKEND / VERSIONS_DIR)
        flagged = [r.render() for r in reports if r.data_loss_risk]
        assert flagged == []

    def test_every_declared_revision_was_analysed(self) -> None:
        chain = declared_migrations(BACKEND)
        reports = analyze_chain(BACKEND / VERSIONS_DIR)
        assert {c.revision for c in chain} == {r.revision for r in reports}
