"""Run with ComfyUI's Python; no import of the ComfyUI plugin entry point."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modules.dlss.runtime_setup import main

if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
