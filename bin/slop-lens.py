#!/usr/bin/env python3
"""Run SlopLens CLI without installing (adds the repo root to sys.path)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from slop_lens.cli import main  # noqa: E402

sys.exit(main())
