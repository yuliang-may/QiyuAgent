"""Tests for VoI scoring logic."""

from lacquertutor.models.slots import HARD_GATE_SLOTS
from lacquertutor.modules.voi_scorer import adjust_scores, rank_scores


class TestAdjustScores:
    def test_hard_gate_floor(self):
        """Hard-gate slots should never go below score 2."""
        raw = {"environment_humidity_pct": 0, "lacquer_system": 1, "ventilation_quality": 0}
        adjusted = adjust_scores(raw)
        assert adjusted["environment_humidity_pct"] == 2  # max(0, 2*1) = 2
        assert adjusted["lacquer_system"] == 2  # max(1, 2*1) = 2
        assert adjusted["ventilation_quality"] == 0  # max(0, 2*0) = 0 (soft slot)

    def test_high_score_preserved(self):
        """Scores above the floor should be preserved."""
        raw = {"environment_humidity_pct": 3, "lacquer_system": 3}
        adjusted = adjust_scores(raw)
        assert adjusted["environment_humidity_pct"] == 3  # max(3, 2) = 3
        assert adjusted["lacquer_system"] == 3

    def test_soft_slot_not_adjusted(self):
        """Soft-gate slots should not get the floor adjustment."""
        raw = {"ventilation_quality": 0, "dust_control_level": 1, "sanding_grit_last": 2}
        adjusted = adjust_scores(raw)
        assert adjusted["ventilation_quality"] == 0
        assert adjusted["dust_control_level"] == 1
        assert adjusted["sanding_grit_last"] == 2

    def test_all_hard_gate_slots_known(self):
        """Verify we know which slots are hard-gated."""
        expected = {
            "lacquer_system",
            "substrate_material",
            "substrate_condition",
            "environment_temperature_c",
            "environment_humidity_pct",
            "curing_method",
            "time_since_last_coat_h",
            "ppe_level",
        }
        assert set(HARD_GATE_SLOTS) == expected


class TestRanking:
    def test_descending_score_order(self):
        scores = {"a": 3, "b": 1, "c": 2}
        ranked = rank_scores(scores)
        assert ranked[0] == ("a", 3)
        assert ranked[1] == ("c", 2)
        assert ranked[2] == ("b", 1)

    def test_hard_gate_tiebreak(self):
        """On equal scores, hard-gate slots come first."""
        scores = {"environment_humidity_pct": 2, "ventilation_quality": 2}
        ranked = rank_scores(scores)
        assert ranked[0][0] == "environment_humidity_pct"

    def test_alphabetical_tiebreak(self):
        """On equal scores and same gate level, sort alphabetically."""
        scores = {"curing_method": 2, "environment_humidity_pct": 2}
        ranked = rank_scores(scores)
        assert ranked[0][0] == "curing_method"

    def test_empty_scores(self):
        ranked = rank_scores({})
        assert ranked == []
