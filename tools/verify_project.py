"""Execute tests and save machine-readable verification evidence."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"]
    proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    log = proc.stdout + proc.stderr
    (ROOT / "tests/latest-results.txt").write_text(log, encoding="utf-8")
    summary = re.search(r"Ran (\d+) tests? in ([\d.]+)s", log)
    counts = Counter(re.findall(r"\(tests\.(\w+)\.[^)]+\) \.\.\. ok", log))
    result = {"timestamp": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(timespec="seconds"),
              "python": platform.python_version(), "os": platform.platform(),
              "qt_platform": "offscreen", "command": command, "exit_code": proc.returncode,
              "tests": int(summary[1]) if summary else 0,
              "seconds": float(summary[2]) if summary else None,
              "passed_by_module": dict(counts), "skipped": len(re.findall(r"\.\.\. skipped", log)),
              "success": proc.returncode == 0 and bool(re.search(r"^OK\s*$", log, re.M))}
    (ROOT / "docs/test-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
