import re


class TextChunker:
    """Create deterministic overlapping chunks, keeping Markdown sections intact."""

    def __init__(self, chunk_size=600, overlap=100):
        if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer.")
        if not isinstance(overlap, int) or isinstance(overlap, bool) or overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap must be non-negative and smaller than chunk_size.")
        self.chunk_size = chunk_size
        self.overlap = overlap

    @staticmethod
    def _sections(text):
        headings = list(re.finditer(r"(?m)^(#{1,6})[ \t]+(.+?)\s*$", text))
        if not headings:
            return [("Overview", text.strip())] if text.strip() else []

        sections = []
        opening = text[: headings[0].start()].strip()
        if opening:
            sections.append(("Overview", opening))
        for index, heading in enumerate(headings):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            body = text[heading.end() : end].strip()
            if body:
                sections.append((heading.group(2).strip(), body))
        return sections

    def chunk(self, text, metadata=None):
        chunks = []
        step = self.chunk_size - self.overlap
        chunk_index = 0
        for section_title, section_text in self._sections(text):
            start = 0
            while start < len(section_text):
                content = section_text[start : start + self.chunk_size].strip()
                if content:
                    if metadata is None:
                        chunks.append(content)
                    else:
                        chunks.append(
                            {
                                "content": f"{section_title}\n\n{content}",
                                "source": metadata.get("source"),
                                "document_name": metadata.get("document_name"),
                                "document_title": metadata.get("title"),
                                "title": section_title,
                                "chunk_index": chunk_index,
                            }
                        )
                        chunk_index += 1
                start += step
        return chunks
