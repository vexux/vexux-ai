from core.contracts.evidence import Evidence, EvidenceSet


def test_evidence_set_limits_redacts_and_discovers_sources():
    evidence = EvidenceSet(max_items=1, max_content_length=4)
    evidence.add(Evidence("rag", "Bearer secret-value", "document"))
    evidence.add(Evidence("sql", "ignored", "structured_data"))

    assert evidence.sources() == ["rag"]
    assert "secret-value" not in evidence.items[0].content
