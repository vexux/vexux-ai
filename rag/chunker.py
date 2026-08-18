class TextChunker:

    def __init__(

        self,

        chunk_size=80,

        overlap=20,

    ):

        self.chunk_size = chunk_size

        self.overlap = overlap

    def chunk(self, text):

        chunks = []

        start = 0

        while start < len(text):

            end = start + self.chunk_size

            chunks.append(text[start:end])

            start += self.chunk_size - self.overlap

        return chunks