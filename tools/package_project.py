"""Build a source ZIP excluding environments, caches, Git and QA artifacts."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".qa", "dist", ".idea", ".vscode"}


def main():
    output = ROOT / "dist/Tiny-Compiler-IDE.zip"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            rel = path.relative_to(ROOT)
            if (path.is_file() and not any(part in EXCLUDE for part in rel.parts)
                    and path.suffix not in (".pyc", ".zip") and not path.name.startswith("~$")):
                archive.write(path, Path("Tiny-Compiler-IDE") / rel)
    print(output)


if __name__ == "__main__":
    main()
