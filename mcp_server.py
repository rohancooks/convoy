"""Exposes Convoy's tools over MCP, so Claude Desktop, Cursor or any MCP client can ask about your day too.
draft_email only writes a draft: Convoy has no permission to send email."""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=True)  # .env wins over stale Windows env vars

from mcp.server.mcpserver import MCPServer  # noqa: E402

import db  # noqa: E402
import tools  # noqa: E402

server = MCPServer("convoy", instructions="Personal data of the user: computer activity, notes, Gmail, Calendar.")
for fn in tools.TOOLS:
    server.add_tool(fn)

if __name__ == "__main__":
    db.init()
    server.run()  # stdio
