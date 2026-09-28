from pathlib import Path
import re


class DocumentLoader:
    """Load supported local knowledge documents in stable path order."""

    SUPPORTED_SUFFIXES = {".md", ".txt"}

    def __init__(self, folder):
        self.folder = Path(folder)

    def load(self):
        if not self.folder.is_dir():
            raise FileNotFoundError(f"RAG document folder does not exist: {self.folder}")

        documents = []
        files = sorted(
            (
                file
                for file in self.folder.rglob("*")
                if file.is_file() and file.suffix.lower() in self.SUPPORTED_SUFFIXES
            ),
            key=lambda file: file.relative_to(self.folder).as_posix().casefold(),
        )
        for file in files:
            content = file.read_text(encoding="utf-8").strip()
            if not content:
                continue
            title_match = re.search(r"(?m)^#\s+(.+?)\s*$", content)
            documents.append(
                {
                    "name": file.name,
                    "document_name": file.stem,
                    "source": file.relative_to(self.folder).as_posix(),
                    "title": title_match.group(1).strip() if title_match else file.stem,
                    "content": content,
                }
            )
        if not documents:
            raise ValueError(f"No non-empty Markdown or text documents found in {self.folder}")
        return documents
