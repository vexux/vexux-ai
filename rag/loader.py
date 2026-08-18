from pathlib import Path


class DocumentLoader:

    def __init__(self, folder):

        self.folder = Path(folder)

    def load(self):

        documents = []

        for file in self.folder.glob("*.txt"):

            text = file.read_text(
                encoding="utf-8"
            )

            documents.append(
                {
                "name": file.name,
                "content": text
                }
            )

        return documents