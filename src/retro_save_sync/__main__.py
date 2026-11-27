import sys

from retro_save_sync.cli import main

if __name__ == "__main__":
    argv = sys.argv[1:]
    # Packaged builds (AppImage / .exe) open the GUI when launched with no arguments.
    if not argv and getattr(sys, "frozen", False):
        argv = ["gui"]
    raise SystemExit(main(argv))
