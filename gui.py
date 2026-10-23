"""Convenient desktop entry point; main.py remains the original CLI."""
from tiny_compiler.ide.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
