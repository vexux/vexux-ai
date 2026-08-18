from pathlib import Path
import yaml


class ConfigLoader:

    @staticmethod
    def load(path: str):

        with open(Path(path), "r", encoding="utf-8") as file:
            return yaml.safe_load(file)