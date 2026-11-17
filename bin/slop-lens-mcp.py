#!/usr/bin/env python3
"""Start the SlopLens MCP stdio server without installing. Point any MCP client here."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from slop_lens.mcp_server import serve  # noqa: E402

serve()
