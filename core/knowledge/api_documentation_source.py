class APIDocumentationKnowledgeSource:
    name = "api_docs"
    description = "Searches an injected API and technical documentation provider."
    capabilities = ["documentation_search", "document_retrieval"]

    def __init__(self, provider):
        self.provider = provider

    def retrieve(self, query, k=None):
        return self.provider.search(query, k=k) if k is not None else self.provider.search(query)

    def normalize(self, records):
        from core.contracts.evidence import Evidence, EvidenceSet
        evidence = EvidenceSet()
        for record in records:
            evidence.add(Evidence(self.name, str(record.get("document", record)), "documentation"))
        return evidence
