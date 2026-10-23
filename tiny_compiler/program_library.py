"""Curated source fixtures and metadata for the supported Tiny dialect."""
from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class ProgramExample:
    id: str
    name: str
    difficulty: str
    description: str
    concepts: list
    path: Path
    sample_input: str
    expected_output: str
    expected_error: str = None
    expected_message: str = ""

    @property
    def source(self):
        return self.path.read_text(encoding="utf-8")


def load_library(examples_root=None):
    base = Path(examples_root) if examples_root else Path(__file__).resolve().parents[1] / "examples"
    rows = json.loads((base / "library.json").read_text(encoding="utf-8"))
    entries, ids = [], set()
    for row in rows:
        path = (base / row["file"]).resolve()
        if base.resolve() not in path.parents:
            raise ValueError("Library source must be inside examples")
        if row["id"] in ids or row["difficulty"] not in ("Beginner", "Intermediate", "Advanced"):
            raise ValueError("Invalid or duplicate library entry")
        ids.add(row["id"])
        entries.append(ProgramExample(row["id"], row["name"], row["difficulty"], row["description"],
                                      row["concepts"], path, row["sample_input"], row["expected_output"],
                                      row.get("expected_error"), row.get("expected_message", "")))
    return entries
