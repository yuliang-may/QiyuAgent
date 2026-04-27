"""Tests for evidence retrieval."""

from lacquertutor.models.evidence import EvidenceStore
from lacquertutor.modules.retrieval import EvidenceRetriever


class TestEvidenceRetrieval:
    def test_stage_filter(self, evidence_store: EvidenceStore):
        retriever = EvidenceRetriever(evidence_store)
        results = retriever.retrieve("curing", k=4)
        assert len(results) == 4
        # At least some should be curing-stage
        curing_count = sum(1 for r in results if r.stage == "curing")
        assert curing_count >= 1

    def test_failure_mode_boost(self, evidence_store: EvidenceStore):
        retriever = EvidenceRetriever(evidence_store)
        results = retriever.retrieve("curing", "tackiness", k=4)
        # Tackiness-specific cards should rank highest
        tackiness_cards = [r for r in results if r.failure_mode == "tackiness"]
        assert len(tackiness_cards) >= 1

    def test_format_summaries(self, evidence_store: EvidenceStore):
        retriever = EvidenceRetriever(evidence_store)
        cards = retriever.retrieve("preparation", k=2)
        text = retriever.format_evidence_summaries(cards)
        assert "E-" in text
        assert "[" in text

    def test_empty_cards(self):
        text = EvidenceRetriever.format_evidence_summaries([])
        assert "无" in text
