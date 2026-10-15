"""Entry point:  python main.py examples/hello.tiny [options]"""
import sys

from tiny_compiler.cli import main

if __name__ == "__main__":
    sys.exit(main())
