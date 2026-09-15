import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 1. S/4HANA Finance Swagger
s4_swagger = {
    "swagger": "2.0",
    "info": {
        "title": "Velora S4HANA Finance MCP",
        "description": "SAP S/4HANA Finance integration for Velora Executive Agent",
        "version": "2.0.0"
    },
    "host": "agenticad-execai-dev-uaen-ca-001.icyriver-9c0a7af6.uaenorth.azurecontainerapps.io",
    "basePath": "/",
    "schemes": ["https"],
    "consumes": ["application/json"],
    "produces": ["application/json"],
    "securityDefinitions": {
        "ApiKeyAuth": {
            "type": "apiKey",
            "name": "x-api-key",
            "in": "header"
        }
    },
    "security": [
        {"ApiKeyAuth": []}
    ],
    "paths": {
        "/health": {
            "get": {
                "summary": "Health Check",
                "operationId": "getHealth",
                "responses": {
                    "200": {"description": "Server healthy"}
                }
            }
        },
        "/mcp/tools": {
            "get": {
                "summary": "List S/4HANA Finance Tools",
                "operationId": "listS4Tools",
                "responses": {
                    "200": {"description": "List of available tools"}
                }
            }
        },
        "/s4__get_receivables_aging": {
            "post": {
                "summary": "Retrieve accounts receivable aging from SAP S/4HANA",
                "operationId": "getReceivablesAging",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "required": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "company_code": {"type": "string", "description": "Company code, e.g. 1000"},
                                "key_date": {"type": "string", "description": "Key date YYYY-MM-DD"},
                                "customer": {"type": "string"},
                                "customer_name": {"type": "string"},
                                "currency": {"type": "string", "default": "AED"}
                            }
                        }
                    }
                ],
                "responses": {
                    "200": {"description": "Receivables aging dataset with Adaptive Card"}
                }
            }
        },
        "/s4__get_payables_aging": {
            "post": {
                "summary": "Retrieve accounts payable aging from SAP S/4HANA",
                "operationId": "getPayablesAging",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "required": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "company_code": {"type": "string"},
                                "key_date": {"type": "string"},
                                "supplier": {"type": "string"},
                                "supplier_name": {"type": "string"},
                                "currency": {"type": "string", "default": "AED"}
                            }
                        }
                    }
                ],
                "responses": {
                    "200": {"description": "Payables aging dataset with Adaptive Card"}
                }
            }
        },
        "/s4__get_budget_consumption": {
            "post": {
                "summary": "Retrieve budget, commitment, and actual expenditure from SAP S/4HANA BudgetConsumSummary",
                "operationId": "getBudgetConsumption",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "required": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "funds_center": {"type": "string", "description": "Funds Center code, e.g. 10CGADHR70"},
                                "fiscal_year": {"type": "string", "description": "Fiscal Year, e.g. 2026"},
                                "period": {"type": "string", "description": "Period 1-12"},
                                "currency": {"type": "string", "default": "AED"},
                                "top": {"type": "integer", "default": 100}
                            }
                        }
                    }
                ],
                "responses": {
                    "200": {"description": "Budget consumption summary dataset with Adaptive Card"}
                }
            }
        }
    }
}


# 2. SAC Analytics Swagger
sac_swagger = {
    "swagger": "2.0",
    "info": {
        "title": "Velora SAC Analytics MCP",
        "description": "SAP Analytics Cloud KPI and Story integration for Velora Executive Agent",
        "version": "1.0.0"
    },
    "host": "sac-analytics-mcp-server.cfapps.eu10-005.hana.ondemand.com",
    "basePath": "/",
    "schemes": ["https"],
    "consumes": ["application/json"],
    "produces": ["application/json"],
    "securityDefinitions": {
        "ApiKeyAuth": {
            "type": "apiKey",
            "name": "x-api-key",
            "in": "header"
        }
    },
    "security": [
        {"ApiKeyAuth": []}
    ],
    "paths": {
        "/health": {
            "get": {
                "summary": "Health Check",
                "operationId": "getHealth",
                "responses": {
                    "200": {"description": "Server healthy"}
                }
            }
        },
        "/mcp/tools": {
            "get": {
                "summary": "List SAC Analytics Tools",
                "operationId": "listSacTools",
                "responses": {
                    "200": {"description": "List of available tools"}
                }
            }
        },
        "/get_sac_kpis": {
            "post": {
                "summary": "Retrieve executive KPIs from SAP Analytics Cloud",
                "operationId": "getSacKpis",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "required": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "domain": {"type": "string", "default": "FINANCE"}
                            }
                        }
                    }
                ],
                "responses": {
                    "200": {"description": "Executive SAC KPIs with Adaptive Card"}
                }
            }
        },
        "/get_sac_story_analytics": {
            "post": {
                "summary": "Fetch SAC Story BI Insights and Variances",
                "operationId": "getSacStoryAnalytics",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "required": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "story_id": {"type": "string", "default": "VELORA_CORP_PERF_2026"}
                            }
                        }
                    }
                ],
                "responses": {
                    "200": {"description": "SAC Story BI insights with Adaptive Card"}
                }
            }
        },
        "/get_sac_model_data": {
            "post": {
                "summary": "Query SAC model measure data",
                "operationId": "getSacModelData",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "required": True,
                        "schema": {
                            "type": "object",
                            "required": ["model_id"],
                            "properties": {
                                "model_id": {"type": "string"},
                                "measures": {"type": "array", "items": {"type": "string"}}
                            }
                        }
                    }
                ],
                "responses": {
                    "200": {"description": "Raw model measure values"}
                }
            }
        }
    }
}

# 3. Facilitator Swagger
facilitator_swagger = {
    "swagger": "2.0",
    "info": {
        "title": "Velora Facilitator MCP",
        "description": "Executive Meeting Synthesis, Calendar Automation & Institutional Memory",
        "version": "1.0.0"
    },
    "host": "facilitator-mcp-server.cfapps.eu10-005.hana.ondemand.com",
    "basePath": "/",
    "schemes": ["https"],
    "consumes": ["application/json"],
    "produces": ["application/json"],
    "securityDefinitions": {
        "ApiKeyAuth": {
            "type": "apiKey",
            "name": "x-api-key",
            "in": "header"
        }
    },
    "security": [
        {"ApiKeyAuth": []}
    ],
    "paths": {
        "/health": {
            "get": {
                "summary": "Health Check",
                "operationId": "getHealth",
                "responses": {"200": {"description": "Server healthy"}}
            }
        },
        "/guide": {
            "get": {
                "summary": "Facilitator Auto-Send Guide",
                "operationId": "getGuide",
                "responses": {"200": {"description": "Setup guide text"}}
            }
        },
        "/get_calendar_meetings": {
            "post": {
                "summary": "Fetch meetings from Outlook/Teams Calendar",
                "operationId": "getCalendarMeetings",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "user_email": {"type": "string"},
                                "timeframe": {"type": "string", "default": "today"}
                            }
                        }
                    }
                ],
                "responses": {"200": {"description": "Calendar meetings"}}
            }
        },
        "/process_calendar_meeting_workflow": {
            "post": {
                "summary": "Process Pre or Post Meeting Synthesis",
                "operationId": "processCalendarMeetingWorkflow",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "meeting_subject": {"type": "string"},
                                "phase": {"type": "string", "default": "POST_MEETING"},
                                "notes": {"type": "string"}
                            }
                        }
                    }
                ],
                "responses": {"200": {"description": "Workflow execution summary"}}
            }
        },
        "/generate_pre_meeting_briefing": {
            "post": {
                "summary": "Synthesize SAP Cross-Connector Meeting Briefing",
                "operationId": "generatePreMeetingBriefing",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "required": True,
                        "schema": {
                            "type": "object",
                            "required": ["meeting_title", "attendees"],
                            "properties": {
                                "meeting_title": {"type": "string"},
                                "attendees": {"type": "array", "items": {"type": "string"}}
                            }
                        }
                    }
                ],
                "responses": {"200": {"description": "Briefing packet"}}
            }
        },
        "/draft_meeting_summary_email": {
            "post": {
                "summary": "Draft Executive Meeting Summary Email",
                "operationId": "draftMeetingSummaryEmail",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "required": True,
                        "schema": {
                            "type": "object",
                            "required": ["topic", "attendees", "key_decisions", "action_items"],
                            "properties": {
                                "topic": {"type": "string"},
                                "attendees": {"type": "array", "items": {"type": "string"}},
                                "key_decisions": {"type": "array", "items": {"type": "string"}},
                                "action_items": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "task": {"type": "string"},
                                            "owner": {"type": "string"},
                                            "due": {"type": "string"}
                                        }
                                    }
                                },
                                "notes": {"type": "string"}
                            }
                        }
                    }
                ],
                "responses": {"200": {"description": "Draft email object ready for review"}}
            }
        },
        "/send_executive_email_via_graph": {
            "post": {
                "summary": "Send Executive Email via Microsoft Graph",
                "operationId": "sendExecutiveEmailViaGraph",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "required": True,
                        "schema": {
                            "type": "object",
                            "required": ["to_recipients", "subject", "body_html"],
                            "properties": {
                                "to_recipients": {"type": "array", "items": {"type": "string"}},
                                "subject": {"type": "string"},
                                "body_html": {"type": "string"},
                                "cc_recipients": {"type": "array", "items": {"type": "string"}},
                                "confirmation_token": {"type": "string"}
                            }
                        }
                    }
                ],
                "responses": {"200": {"description": "Email dispatch confirmation"}}
            }
        }
    }
}

with open(BASE_DIR / "mcp-apps" / "ask-s4hana" / "s4-connector-swagger.json", "w") as f:
    json.dump(s4_swagger, f, indent=2)

with open(BASE_DIR / "mcp-apps" / "ask-sac" / "sac-connector-swagger.json", "w") as f:
    json.dump(sac_swagger, f, indent=2)

with open(BASE_DIR / "mcp-apps" / "ask-facilitator" / "facilitator-connector-swagger.json", "w") as f:
    json.dump(facilitator_swagger, f, indent=2)

print("Created OpenAPI Swagger definitions for S/4HANA, SAC, and Facilitator Custom Connectors.")
