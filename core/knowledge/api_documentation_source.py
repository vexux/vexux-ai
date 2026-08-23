class APIDocumentationKnowledgeSource:
    name = "api_docs"
    description = "Searches an injected API and technical documentation provider."
    capabilities = ["documentation_search", "document_retrieval"]

    def __init__(self, provider):
        self.provider = provider

    def retrieve(self, query, k=None):
        return self.provider.search(query, k=k) if k is not None else self.provider.search(query)
