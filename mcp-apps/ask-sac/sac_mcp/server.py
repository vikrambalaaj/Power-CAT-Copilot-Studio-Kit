import hmac
import uvicorn
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from typing import Any, Dict, Optional

from sac_mcp.settings import settings
from sac_mcp.tools import ALL_TOOLS

app = FastAPI(title="SAP Analytics Cloud MCP Server", version="0.1.0")

PUBLIC_PATHS = {"/health", "/"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path not in PUBLIC_PATHS:
        if not settings.allow_anonymous:
            supplied = request.headers.get("x-api-key", "")
            auth_header = request.headers.get("authorization", "")
            if not supplied and auth_header.lower().startswith("bearer "):
                supplied = auth_header[7:].strip()
            if not settings.mcp_api_key or not hmac.compare_digest(supplied, settings.mcp_api_key):
                return JSONResponse(
                    {
                        "status": "error",
                        "code": "UNAUTHORIZED",
                        "message": "Authentication required. Please provide a valid API key.",
                    },
                    status_code=401,
                )
    return await call_next(request)


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


@app.api_route("/get_sac_kpis", methods=["GET", "POST"])
@app.api_route("/tools/get_sac_kpis", methods=["GET", "POST"])
async def rest_get_sac_kpis(domain: str = "FINANCE", req: Optional[Request] = None):
    if req and req.method == "POST":
        try:
            b = await req.json()
            domain = b.get("domain", domain)
        except Exception:
            pass
    tool = next(t for t in ALL_TOOLS if t["name"] == "get_sac_kpis")
    return await tool["handler"](domain=domain)


@app.api_route("/get_sac_story_analytics", methods=["GET", "POST"])
@app.api_route("/tools/get_sac_story_analytics", methods=["GET", "POST"])
async def rest_get_sac_story(story_id: str = "VELORA_CORP_PERF_2026", req: Optional[Request] = None):
    if req and req.method == "POST":
        try:
            b = await req.json()
            story_id = b.get("story_id", story_id)
        except Exception:
            pass
    tool = next(t for t in ALL_TOOLS if t["name"] == "get_sac_story_analytics")
    return await tool["handler"](story_id=story_id)


@app.api_route("/get_sac_model_data", methods=["GET", "POST"])
@app.api_route("/tools/get_sac_model_data", methods=["GET", "POST"])
async def rest_get_sac_model(model_id: str = "", req: Optional[Request] = None):
    measures = None
    if req and req.method == "POST":
        try:
            b = await req.json()
            model_id = b.get("model_id", model_id)
            measures = b.get("measures")
        except Exception:
            pass
    tool = next(t for t in ALL_TOOLS if t["name"] == "get_sac_model_data")
    return await tool["handler"](model_id=model_id, measures=measures)


def main():
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
