"""Runner script for Facilitator MCP server."""
import sys
import uvicorn

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run("facilitator_mcp.server:app", host="0.0.0.0", port=port, log_level="info")
