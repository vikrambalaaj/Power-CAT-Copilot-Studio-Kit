import uvicorn
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Any, Dict, Optional

from sac_mcp.settings import settings
from sac_mcp.tools import ALL_TOOLS

app = FastAPI(title="SAP Analytics Cloud MCP Server", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origins] if settings.cors_origins != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "sac-analytics-mcp-server", "version": "0.1.0"}


@app.get("/mcp/tools")
async def list_tools():
    return {
        "tools": [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            }
            for t in ALL_TOOLS
        ]
    }


@app.post("/mcp")
@app.post("/mcp/call")
async def call_mcp(req: Request, authorization: Optional[str] = Header(None), x_api_key: Optional[str] = Header(None)):
    body = await req.json()
    tool_name = body.get("name") or body.get("method")
    args = body.get("arguments") or body.get("params") or {}

    tool = next((t for t in ALL_TOOLS if t["name"] == tool_name), None)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    try:
        result = await tool["handler"](**args)
        return {"result": result, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def main():
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
