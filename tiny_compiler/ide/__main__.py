"""Launch with python -m tiny_compiler.ide [optional source file]."""
import sys
from pathlib import Path


def main():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("The desktop IDE requires PySide6. Install it with:\n"
              "  python -m pip install -r requirements.txt", file=sys.stderr)
        return 1
    from .window import MainWindow
    app = QApplication(sys.argv)
    app.setApplicationName("Tiny Compiler IDE")
    window = MainWindow()
    if len(sys.argv) > 1:
        window.load_path(Path(sys.argv[1]))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
