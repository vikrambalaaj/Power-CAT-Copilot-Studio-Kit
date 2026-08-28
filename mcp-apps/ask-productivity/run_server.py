#!/usr/bin/env python3
"""Run entry point for Velora Productivity Agent MCP Server."""
import uvicorn
import os

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8004"))
    uvicorn.run("productivity_mcp.server:app", host="0.0.0.0", port=port, reload=False)
