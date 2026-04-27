"""Tests for contract enrichment heuristics."""

from lacquertutor.models.contract import PlanContract, PlanStep
from lacquertutor.models.evidence import EvidenceCard, EvidencePointer
from lacquertutor.models.slots import create_slot_state
from lacquertutor.modules.contract_quality import ContractEnricher


def _sample_evidence() -> list[EvidenceCard]:
    return [
        EvidenceCard(
            evidence_id="E-PREP-01",
            stage="preparation",
            summary_en="Prep evidence",
            pointer=EvidencePointer(doc_id="doc1"),
        ),
        EvidenceCard(
            evidence_id="E-SAFE-01",
            stage="general",
            summary_en="Safety evidence",
            pointer=EvidencePointer(doc_id="doc2"),
        ),
    ]


def test_enricher_adds_contract_scaffolding_for_critical_steps():
    slot_state = create_slot_state()
    slot_state.fill("substrate_material", "wood")
    slot_state.fill("substrate_condition", "raw")
    slot_state.fill("lacquer_system", "urushi")

    contract = PlanContract(
        steps=[
            PlanStep(step_number=1, action="Apply first lacquer coat"),
            PlanStep(step_number=2, action="Wait for cure"),
        ]
    )

    enriched = ContractEnricher().enrich(
        contract,
        slot_state,
        _sample_evidence(),
        task_type="planning",
        stage="preparation",
    )

    assert any(step.is_irreversible for step in enriched.steps)
    assert enriched.checkpoints, "Critical steps should get checkpoints"
    assert enriched.high_risk_warnings, "Critical steps should get warnings"
    assert enriched.contingencies, "Critical steps should get contingencies"
    assert all(step.evidence_refs for step in enriched.steps)
