"""FastMCP and FastAPI Service for Velora Productivity Agent."""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from .models import HandoffRequest, HandoffResponse
from .tools_m365_reads import (
    search_mail,
    get_mail_thread,
    summarize_priority_mail,
    find_mail_follow_ups,
    list_calendar_events,
    get_meeting_details,
    check_availability,
    get_meeting_context,
    search_teams_messages,
    get_channel_context,
    get_chat_context,
    find_teams_follow_ups,
    list_my_planner_tasks,
    list_plan_tasks,
    get_planner_task,
    find_overdue_tasks,
    get_daily_executive_briefing,
    plan_my_day,
    get_quick_action_checklist,
    get_executive_attention,
    get_pre_meeting_brief,
    get_end_of_day_digest,
    get_meeting_action_tracker,
)
from .tools_m365_writes import (
    prepare_email,
    send_approved_email,
    prepare_email_reply,
    send_approved_email_reply,
    prepare_meeting_creation,
    create_approved_meeting,
    prepare_meeting_update,
    update_approved_meeting,
    prepare_meeting_cancellation,
    cancel_approved_meeting,
    prepare_teams_chat_message,
    send_approved_teams_chat_message,
    prepare_teams_channel_post,
    send_approved_teams_channel_post,
    prepare_planner_task,
    create_approved_planner_task,
    prepare_planner_task_update,
    update_approved_planner_task,
    prepare_planner_completion,
    complete_approved_planner_task,
    prepare_daily_briefing_email,
    send_approved_daily_briefing_email,
    send_daily_briefing_email,
    prepare_end_of_day_wrapup_email,
    prepare_automation_subscription,
    confirm_automation_subscription,
    revoke_automation_subscription,
    prepare_meeting_actions,
    create_approved_meeting_actions,
)
from .tools_recommendations import (
    evaluate_verified_kpi_snapshot,
    list_recommendations,
)
from .feedback_service import (
    record_recommendation_feedback,
    get_rule_feedback_summary,
    list_feedback_for_recommendation,
)

from pathlib import Path

# The connector spec the Copilot Studio plugin fetches. It lives beside the
# package so it ships with the app and is served, not just committed.
CONNECTOR_SPEC_PATH = Path(__file__).parent.parent / "productivity-connector-swagger.json"

try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse
    app = FastAPI(
        title="Velora Productivity Agent MCP",
        description="Authorized Microsoft 365, Work IQ, Outlook, Calendar, Teams, and Planner Connected Agent.",
        version="1.0.0",
    )
except ImportError:
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.exceptions import HTTPException

    class StarletteAppWrapper(Starlette):
        def get(self, path: str):
            def decorator(func):
                async def asgi_endpoint(request: Request):
                    try:
                        res = await func() if asyncio.iscoroutinefunction(func) else func()
                        return JSONResponse(res)
                    except HTTPException as exc:
                        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
                    except Exception as exc:
                        return JSONResponse({"detail": str(exc)}, status_code=500)
                self.add_route(path, asgi_endpoint, methods=["GET"])
                return func
            return decorator

        def post(self, path: str):
            def decorator(func):
                async def asgi_endpoint(request: Request):
                    from .models import HandoffRequest, HandoffResponse
                    try:
                        body = await request.json()
                        req_obj = HandoffRequest(**body)
                    except Exception as e:
                        return JSONResponse({"error": f"Invalid JSON payload: {e}"}, status_code=400)
                    try:
                        resp = await func(req_obj, request)
                        return JSONResponse(resp.model_dump() if hasattr(resp, "model_dump") else resp.__dict__)
                    except HTTPException as exc:
                        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
                    except Exception as exc:
                        return JSONResponse({"detail": str(exc)}, status_code=500)
                self.add_route(path, asgi_endpoint, methods=["POST"])
                return func
            return decorator

    app = StarletteAppWrapper()


@app.get("/productivity-connector-swagger.json")
async def connector_spec() -> Dict[str, Any]:
    """Serve the connector spec fetched by the Copilot Studio productivity plugin.

    Without this route the plugin's spec URL 404s, Copilot discovers no operations,
    and the parent agent reports Microsoft 365 as unavailable even though every
    handoff operation below is implemented and running.
    """
    return json.loads(CONNECTOR_SPEC_PATH.read_text(encoding="utf-8"))


@app.get("/health")
async def health_check(request: Request = None) -> Any:
    from fastapi.responses import JSONResponse
    is_prod = (
        os.getenv("VELORA_ENV", "").lower() in ("production", "prod")
        or os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")
        or os.getenv("NODE_ENV", "").lower() in ("production", "prod")
    )
    has_approval_secret = bool(os.getenv("VELORA_APPROVAL_HMAC_SECRET"))
    is_ready = True
    readiness_reason = "Ready"
    if is_prod and not has_approval_secret:
        is_ready = False
        readiness_reason = "Missing required VELORA_APPROVAL_HMAC_SECRET"

    payload = {
        "status": "HEALTHY" if is_ready else "DEGRADED",
        "ready": is_ready,
        "readiness_reason": readiness_reason,
        "service": "Velora Productivity Agent",
        "version": "1.0.0",
        "capabilities": ["Mail", "Calendar", "Teams", "Planner", "WorkIQ", "DataverseAudit"],
        "audit_table": "cre2f_veloraagentauditlog",
    }
    if not is_ready:
        return JSONResponse(payload, status_code=503)
    return payload


# --- Hand-off Router Endpoint (Section 12 & 13) ---

@app.post("/handoff")
async def handle_parent_handoff(request: HandoffRequest, raw_request: Request = None) -> HandoffResponse:
    """Entry point for Copilot Studio Parent to Connected Productivity Agent calls.
    
    Binds all requests to verified identity before routing (WP02, AIDEV-01, AIDEV-05).
    Rejects absent/invalid tokens with HTTP 401 and conflicting body identity with HTTP 403.
    """
    from shared_mcp.identity import (
        extract_verified_identity,
        verify_body_identity_binding,
        AuthenticationError,
        AuthorizationError,
    )
    from shared_mcp.kill_switch import check_kill_switch, KillSwitchActiveError

    identity = None
    if raw_request is not None:
        try:
            body_bytes = await raw_request.body()
            identity = extract_verified_identity(
                dict(raw_request.headers),
                method=raw_request.method,
                path=raw_request.url.path,
                body=body_bytes,
                require_user_principal=request.operation.upper() not in ("EVALUATE_VERIFIED_KPI_SNAPSHOT", "EVALUATEVERIFIEDKPISNAPSHOT"),
            )
            if identity.is_user:
                verify_body_identity_binding(identity, body_user_id=request.userObjectId, body_email=request.userEmail)
                uid = identity.object_id
                email = identity.display_email or request.userEmail or "executive@velora.ae"
            else:
                uid = identity.object_id
                email = identity.display_email or request.userEmail or "workload@velora.ae"

            # Enforce tenant matching to prevent cross-tenant parameter forgery
            if request.tenantId and request.tenantId.strip() != identity.tenant_id:
                raise AuthorizationError(
                    f"Request body tenantId '{request.tenantId}' does not match token tenantId '{identity.tenant_id}'"
                )
            request.tenantId = identity.tenant_id
            if request.parameters and isinstance(request.parameters, dict):
                p_tid = request.parameters.get("tenantId")
                if p_tid and p_tid.strip() != identity.tenant_id:
                    raise AuthorizationError(
                        f"Parameters tenantId '{p_tid}' does not match token tenantId '{identity.tenant_id}'"
                    )
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=exc.message)
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=exc.message)
    else:
        is_test_env = (
            os.getenv("ALLOW_OFFLINE_TEST_TOKENS", "").lower() in ("1", "true", "yes")
            or os.getenv("PYTEST_CURRENT_TEST") is not None
            or os.getenv("MOCK_M365") is not None
        )
        if not is_test_env:
            raise HTTPException(status_code=401, detail="Missing Authorization Bearer token")
        uid = request.userObjectId
        email = request.userEmail

    op = request.operation.upper()

    # Enforce Kill-Switch evaluation at dispatch boundary
    try:
        client_app_id = identity.client_application_id if identity else None
        tenant_id = identity.tenant_id if identity else "velora-tenant"
        check_kill_switch(tool_name=op, client_id=client_app_id, tenant_id=tenant_id)
    except KillSwitchActiveError as exc:
        raise HTTPException(status_code=403, detail=exc.message)
    params = request.parameters
    corr_id = request.rootCorrelationId
    conv_id = request.conversationId
    turn_id = request.turnId

    try:
        if op in ("SEARCH_MAIL", "SEARCHMAIL"):
            res = await search_mail(
                query=params.get("query", ""),
                dateFrom=params.get("dateFrom", params.get("receivedAfter")),
                dateTo=params.get("dateTo", params.get("receivedBefore")),
                unreadOnly=params.get("unreadOnly", False),
                timeZone=params.get("timeZone", request.userTimezone or "Asia/Dubai"),
                maximumResults=params.get("maximumResults", 10),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res["structuredResult"],
            )

        elif op in ("PREPARE_EMAIL", "PREPAREEMAIL"):
            to_val = params.get("recipientNames") or params.get("to")
            if not to_val:
                return HandoffResponse(
                    status="VALIDATION_ERROR",
                    approvalRequired=False,
                    resultSummary="Missing required field: recipients ('to' or 'recipientNames') must be explicitly provided.",
                    correlationId=corr_id,
                    warnings=["Recipients were not provided."],
                )
            if isinstance(to_val, str):
                to_val = [r.strip() for r in to_val.split(",") if r.strip()]
            res = await prepare_email(
                to=to_val,
                subject=params.get("subject", "Executive Follow-up"),
                body=params.get("body", params.get("bodySource", "")),
                cc=params.get("cc"),
                attachments=params.get("attachments"),
                sensitivity=request.dataClassification or "CONFIDENTIAL",
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("SEND_APPROVED_EMAIL", "SENDAPPROVEDEMAIL"):
            res = await send_approved_email(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("PREPARE_MEETING_CREATION", "PREPAREMEETING"):
            att_val = params.get("attendees")
            if not att_val:
                return HandoffResponse(
                    status="VALIDATION_ERROR",
                    approvalRequired=False,
                    resultSummary="Missing required field: 'attendees' must be explicitly provided.",
                    correlationId=corr_id,
                    warnings=["Meeting attendees were not provided."],
                )
            if isinstance(att_val, str):
                att_val = [a.strip() for a in att_val.split(",") if a.strip()]
            start_time = params.get("startTime")
            end_time = params.get("endTime")
            if not start_time or not end_time:
                return HandoffResponse(
                    status="VALIDATION_ERROR",
                    approvalRequired=False,
                    resultSummary="Missing required fields: 'startTime' and 'endTime' must be explicitly provided.",
                    correlationId=corr_id,
                    warnings=["Meeting startTime or endTime was not provided."],
                )
            res = await prepare_meeting_creation(
                subject=params.get("subject", "Executive Strategy Alignment"),
                attendees=att_val,
                startTime=start_time,
                endTime=end_time,
                timeZone=request.userTimezone or "Asia/Dubai",
                location=params.get("location", "Microsoft Teams Meeting"),
                body=params.get("body", ""),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("CREATE_APPROVED_MEETING", "CREATEAPPROVEDMEETING"):
            res = await create_approved_meeting(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("PLAN_MY_DAY", "PLANMYDAY"):
            res = await plan_my_day(
                userTimezone=params.get("userTimezone") or request.userTimezone or "Asia/Dubai",
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res["structuredResult"],
            )

        elif op in ("QUICK_ACTION_CHECKLIST", "QUICKACTIONCHECKLIST", "CHECKLIST"):
            res = await get_quick_action_checklist(
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res["structuredResult"],
            )

        elif op in ("PREPARE_END_OF_DAY_WRAPUP_EMAIL", "PREPAREENDOFDAYWRAPUPEMAIL", "WRAPUP_EMAIL"):
            res = await prepare_end_of_day_wrapup_email(
                userTimezone=params.get("userTimezone") or request.userTimezone or "Asia/Dubai",
                recipientOverride=params.get("recipientOverride") or params.get("to"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("GET_DAILY_EXECUTIVE_BRIEFING", "GETDAILYBRIEFING", "DAILY_BRIEFING", "BRIEFING"):
            res = await get_daily_executive_briefing(
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res["structuredResult"],
            )

        elif op in ("PREPARE_DAILY_BRIEFING_EMAIL", "PREPAREDAILYBRIEFINGEMAIL"):
            res = await prepare_daily_briefing_email(
                recipientOverride=params.get("recipientOverride") or params.get("to"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("SEND_APPROVED_DAILY_BRIEFING_EMAIL", "SENDAPPROVEDDAILYBRIEFINGEMAIL"):
            res = await send_approved_daily_briefing_email(
                confirmationToken=params.get("confirmationToken", ""),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("SEND_DAILY_BRIEFING_EMAIL", "SENDDAILYBRIEFINGEMAIL"):
            res = await send_daily_briefing_email(
                recipientOverride=params.get("recipientOverride") or params.get("to"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("GET_PRE_MEETING_BRIEF", "GETPREMEETINGBRIEF", "PRE_MEETING_BRIEF"):
            res = await get_pre_meeting_brief(
                eventId=params.get("eventId") or params.get("id"),
                leadTimeMinutes=int(params.get("leadTimeMinutes", 15)),
                userTimezone=params.get("timezone", request.userTimezone or "Asia/Dubai"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res["structuredResult"],
            )

        elif op in ("GET_END_OF_DAY_DIGEST", "GETENDOFDAYDIGEST", "END_OF_DAY_DIGEST", "EOD_DIGEST"):
            res = await get_end_of_day_digest(
                localSchedule=params.get("localSchedule") or params.get("schedule"),
                userTimezone=params.get("timezone", request.userTimezone or "Asia/Dubai"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res["structuredResult"],
            )

        elif op in ("PREPARE_AUTOMATION_SUBSCRIPTION", "PREPAREAUTOMATIONSUBSCRIPTION"):
            res = await prepare_automation_subscription(
                kind=params.get("kind", "MORNING"),
                mailbox=params.get("mailbox") or email,
                recipients=params.get("recipients"),
                localSchedule=params.get("localSchedule") or params.get("schedule"),
                timezone=params.get("timezone", request.userTimezone or "Asia/Dubai"),
                meetingFilters=params.get("meetingFilters"),
                leadTimeMinutes=int(params.get("leadTimeMinutes", 15)),
                horizonHours=int(params.get("horizonHours", 24)),
                channel=params.get("channel", "EMAIL"),
                validUntil=params.get("validUntil"),
                allowedDataScope=params.get("allowedDataScope"),
                quietHoursPolicy=params.get("quietHoursPolicy", "SUPPRESS"),
                missedRunPolicy=params.get("missedRunPolicy", "SKIP"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
                tenantId=getattr(request, "tenantId", None) or params.get("tenantId") or "velora-tenant",
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("CONFIRM_AUTOMATION_SUBSCRIPTION", "CONFIRMAUTOMATIONSUBSCRIPTION"):
            token = params.get("confirmationToken") or params.get("token") or getattr(request, "confirmationToken", None) or ""
            sub_id = params.get("subscriptionId", "")
            res = await confirm_automation_subscription(
                confirmationToken=token,
                subscriptionId=sub_id,
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
                tenantId=getattr(request, "tenantId", None) or params.get("tenantId") or "velora-tenant",
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId")},
            )

        elif op in ("REVOKE_AUTOMATION_SUBSCRIPTION", "REVOKEAUTOMATIONSUBSCRIPTION"):
            sub_id = params.get("subscriptionId", "")
            res = await revoke_automation_subscription(
                subscriptionId=sub_id,
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
                tenantId=getattr(request, "tenantId", None) or params.get("tenantId") or "velora-tenant",
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId")},
            )

        elif op in ("EVALUATE_VERIFIED_KPI_SNAPSHOT", "EVALUATEVERIFIEDKPISNAPSHOT"):
            is_workload = (
                (identity and "WORKLOAD_AUTHORIZED" in identity.roles)
                or (identity and "Velora_Admin" in identity.roles)
                or (identity and "Admin" in identity.roles)
                or (identity and "KPI.Ingest" in identity.scopes)
            )
            if not is_workload:
                raise HTTPException(
                    status_code=403,
                    detail="EVALUATE_VERIFIED_KPI_SNAPSHOT requires workload-authorized identity or KPI.Ingest application permission",
                )
            snap_payload = params.get("snapshot") or params
            effective_tenant = identity.tenant_id if identity else (getattr(request, "tenantId", None) or "velora-tenant")
            res = await evaluate_verified_kpi_snapshot(
                snapshot=snap_payload,
                caller_role="WORKLOAD_AUTHORIZED",
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
                tenantId=effective_tenant,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res.get("auditStatus", "PERSISTED"),
                warnings=res.get("warnings", []),
                structuredResult={
                    "snapshotId": res.get("snapshotId"),
                    "recommendationsCount": res.get("recommendationsCount", 0),
                    "recommendations": res.get("recommendations", []),
                },
                claims=res.get("claims", []),
                sources=res.get("sources", []),
                confidence=res.get("confidence"),
            )

        elif op in ("LIST_RECOMMENDATIONS", "LISTRECOMMENDATIONS"):
            res = await list_recommendations(
                status=params.get("status"),
                category=params.get("category"),
                kpiCode=params.get("kpiCode") or params.get("kpi"),
                limit=int(params.get("limit", 50)),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
                tenantId=getattr(request, "tenantId", None) or params.get("tenantId") or "velora-tenant",
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res["structuredResult"],
                claims=res.get("claims", []),
                sources=res.get("sources", []),
                confidence=res.get("confidence"),
            )

        elif op in ("RECORD_RECOMMENDATION_FEEDBACK", "RECORDRECOMMENDATIONFEEDBACK", "SUBMIT_RECOMMENDATION_FEEDBACK"):
            try:
                res = await record_recommendation_feedback(
                    recommendation_id=params.get("recommendationId") or params.get("recommendation_id", ""),
                    is_useful=bool(params.get("isUseful", params.get("is_useful", True))),
                    feedback_type=params.get("feedbackType") or params.get("feedback_type", "TIMELY_AND_ACCURATE"),
                    comment=params.get("comment"),
                    idempotency_key=params.get("idempotencyKey") or params.get("idempotency_key"),
                    verified_identity=identity,
                    user_email=email,
                    user_object_id=uid,
                    tenant_id=getattr(request, "tenantId", None) or params.get("tenantId") or (identity.tenant_id if identity else "velora-tenant"),
                    body_reviewer=params.get("reviewer") or params.get("bodyReviewer"),
                    root_correlation_id=corr_id,
                    conversation_id=conv_id,
                    turn_id=turn_id,
                )
                return HandoffResponse(
                    status=res.get("status", "SUCCESS"),
                    approvalRequired=False,
                    resultSummary=res.get("message", "Feedback recorded successfully."),
                    correlationId=corr_id,
                    auditStatus=res.get("auditStatus", "PERSISTED"),
                    warnings=[],
                    structuredResult=res,
                )
            except Exception as ex:
                return HandoffResponse(
                    status="ERROR",
                    approvalRequired=False,
                    resultSummary=str(ex),
                    correlationId=corr_id,
                    auditStatus="FAILED",
                    warnings=[str(ex)],
                )

        elif op in ("GET_RULE_FEEDBACK_SUMMARY", "GETRULEFEEDBACKSUMMARY"):
            rule_code = params.get("ruleCode") or params.get("rule_code", "")
            tenant = getattr(request, "tenantId", None) or params.get("tenantId") or (identity.tenant_id if identity else "velora-tenant")
            summary = get_rule_feedback_summary(rule_code=rule_code, tenant_id=tenant)
            return HandoffResponse(
                status=summary["status"],
                approvalRequired=False,
                resultSummary=f"Feedback summary for rule {rule_code}: total={summary['totalFeedback']}, usefulRatio={summary['usefulRatio']}",
                correlationId=corr_id,
                auditStatus="PERSISTED",
                warnings=[],
                structuredResult=summary,
            )

        elif op in ("GET_MAIL_THREAD", "GETMAILTHREAD"):
            res = await get_mail_thread(
                threadId=params.get("threadId", params.get("conversationId", "")),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("SUMMARIZE_PRIORITY_MAIL", "SUMMARIZEPRIORITYMAIL"):
            res = await summarize_priority_mail(
                maximumResults=params.get("maximumResults", 5),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
                rubricPolicy=params.get("rubricPolicy"),
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res.get("structuredResult"),
                claims=res.get("claims", []),
                sources=res.get("sources", []),
            )

        elif op in ("GET_EXECUTIVE_ATTENTION", "GETEXECUTIVEATTENTION", "EXECUTIVE_ATTENTION", "ATTENTION"):
            res = await get_executive_attention(
                lookbackHours=params.get("lookbackHours", 48),
                maximumResults=params.get("maximumResults", 10),
                policyId=params.get("policyId"),
                rubricPolicy=params.get("rubricPolicy"),
                includeCalendar=params.get("includeCalendar", True),
                includeTasks=params.get("includeTasks", True),
                timeZone=params.get("timeZone", request.userTimezone or "Asia/Dubai"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res.get("structuredResult"),
                claims=res.get("claims", []),
                sources=res.get("sources", []),
            )

        elif op in ("FIND_MAIL_FOLLOW_UPS", "FINDMAILFOLLOWUPS"):
            res = await find_mail_follow_ups(
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("PREPARE_EMAIL_REPLY", "PREPAREEMAILREPLY"):
            res = await prepare_email_reply(
                threadId=params.get("threadId", params.get("messageId", "")),
                body=params.get("body", params.get("replyBody", "")),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("SEND_APPROVED_EMAIL_REPLY", "SENDAPPROVEDEMAILREPLY"):
            res = await send_approved_email_reply(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("LIST_CALENDAR_EVENTS", "LISTCALENDAREVENTS", "LIST_EVENTS", "CALENDAR"):
            res = await list_calendar_events(
                dateFrom=params.get("dateFrom", params.get("startDateTime", params.get("startTime"))),
                dateTo=params.get("dateTo", params.get("endDateTime", params.get("endTime"))),
                timeZone=params.get("timeZone", request.userTimezone or "Asia/Dubai"),
                includeCancelled=params.get("includeCancelled", False),
                maximumResults=params.get("maximumResults", 50),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("GET_MEETING_DETAILS", "GETMEETINGDETAILS"):
            res = await get_meeting_details(
                eventId=params.get("eventId", ""),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("CHECK_AVAILABILITY", "CHECKAVAILABILITY"):
            res = await check_availability(
                attendees=params.get("attendees", []),
                startTime=params.get("startTime", "2026-08-27T10:00:00Z"),
                endTime=params.get("endTime", "2026-08-27T11:00:00Z"),
                timeZone=params.get("timeZone", request.userTimezone or "Asia/Dubai"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("GET_MEETING_CONTEXT", "GETMEETINGCONTEXT"):
            res = await get_meeting_context(
                subjectOrId=params.get("subjectOrId", params.get("subjectOrEventId", params.get("subject", ""))),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("GET_MEETING_ACTION_TRACKER", "GETMEETINGACTIONTRACKER", "MEETING_ACTION_TRACKER", "TRACKER"):
            res = await get_meeting_action_tracker(
                meetingId=params.get("meetingId") or params.get("meeting_id"),
                sourceVersion=params.get("sourceVersion") or params.get("source_version"),
                userEmail=email,
                tenantId=getattr(request, "tenantId", None) or params.get("tenantId") or "velora-aviation",
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("PREPARE_MEETING_ACTIONS", "PREPAREMEETINGACTIONS"):
            res = await prepare_meeting_actions(
                meetingId=params.get("meetingId") or params.get("meeting_id") or params.get("eventId") or "",
                sourceVersion=params.get("sourceVersion") or params.get("source_version") or "1.0",
                notesOverride=params.get("notesOverride") or params.get("notes"),
                transcriptOverride=params.get("transcriptOverride") or params.get("transcript"),
                targetPlan=params.get("targetPlan") or params.get("planName") or "Executive Strategic Initiatives",
                targetBucket=params.get("targetBucket") or params.get("bucketName") or "Q3 Deliverables",
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
                tenantId=getattr(request, "tenantId", None) or params.get("tenantId") or "velora-aviation",
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res.get("approvalRequired", False),
                resultSummary=res["resultSummary"],
                confirmationToken=res.get("confirmationToken"),
                correlationId=corr_id,
                auditStatus=res.get("auditStatus", "PERSISTED"),
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("CREATE_APPROVED_MEETING_ACTIONS", "CREATEAPPROVEDMEETINGACTIONS", "CONFIRM_MEETING_ACTIONS"):
            token = params.get("confirmationToken") or params.get("token") or getattr(request, "confirmationToken", None) or ""
            preview = params.get("previewDetails") or params.get("preview") or {}
            res = await create_approved_meeting_actions(
                confirmationToken=token,
                previewDetails=preview,
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
                tenantId=getattr(request, "tenantId", None) or params.get("tenantId") or "velora-aviation",
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res.get("auditStatus", "PERSISTED"),
                warnings=res.get("warnings", []),
                structuredResult=res,
            )

        elif op in ("PREPARE_MEETING_UPDATE", "PREPAREMEETINGUPDATE"):
            res = await prepare_meeting_update(
                eventId=params.get("eventId", ""),
                updates=params.get("updates") or {
                    k: v for k, v in {
                        "subject": params.get("subject"),
                        "attendees": params.get("attendees"),
                        "startTime": params.get("startTime"),
                        "endTime": params.get("endTime"),
                        "body": params.get("body"),
                    }.items() if v is not None
                },
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("UPDATE_APPROVED_MEETING", "UPDATEAPPROVEDMEETING"):
            res = await update_approved_meeting(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("PREPARE_MEETING_CANCELLATION", "PREPAREMEETINGCANCELLATION"):
            res = await prepare_meeting_cancellation(
                eventId=params.get("eventId", ""),
                reason=params.get("reason", params.get("cancellationReason", "Cancelled by executive")),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("CANCEL_APPROVED_MEETING", "CANCELAPPROVEDMEETING"):
            res = await cancel_approved_meeting(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("SEARCH_TEAMS_MESSAGES", "SEARCHTEAMS", "SEARCH_TEAMS"):
            res = await search_teams_messages(
                query=params.get("query", ""),
                maximumResults=params.get("maximumResults", 10),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("GET_CHANNEL_CONTEXT", "GETCHANNELCONTEXT"):
            res = await get_channel_context(
                teamName=params.get("teamName", ""),
                channelName=params.get("channelName", ""),
                maximumResults=params.get("maximumResults", params.get("maximumMessages", 10)),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("GET_CHAT_CONTEXT", "GETCHATCONTEXT"):
            res = await get_chat_context(
                chatId=params.get("chatId", params.get("participantEmail", "")),
                maximumResults=params.get("maximumResults", params.get("maximumMessages", 10)),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("FIND_TEAMS_FOLLOW_UPS", "FINDTEAMSFOLLOWUPS"):
            res = await find_teams_follow_ups(
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("PREPARE_TEAMS_CHAT_MESSAGE", "PREPARETEAMSCHAT"):
            res = await prepare_teams_chat_message(
                chatId=params.get("chatId", params.get("recipientEmail", "leadership@velora.ae")),
                messageContent=params.get("messageContent", params.get("messageText", params.get("message", ""))),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("SEND_APPROVED_TEAMS_CHAT_MESSAGE", "SENDAPPROVEDTEAMSCHAT"):
            res = await send_approved_teams_chat_message(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("PREPARE_TEAMS_CHANNEL_POST", "PREPARETEAMSCHANNELPOST"):
            res = await prepare_teams_channel_post(
                teamName=params.get("teamName", "Executive Leadership Team"),
                channelName=params.get("channelName", "General"),
                messageContent=params.get("messageContent", params.get("postBody", params.get("body", ""))),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("SEND_APPROVED_TEAMS_CHANNEL_POST", "SENDAPPROVEDTEAMSCHANNELPOST"):
            res = await send_approved_teams_channel_post(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("LIST_MY_PLANNER_TASKS", "LISTMYPLANNER", "PLANNER_TASKS", "TASKS"):
            res = await list_my_planner_tasks(
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("LIST_PLAN_TASKS", "LISTPLANTASKS"):
            res = await list_plan_tasks(
                planName=params.get("planName", params.get("planTitle", "Executive Strategic Initiatives")),
                planId=params.get("planId"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("GET_PLANNER_TASK", "GETPLANNER"):
            res = await get_planner_task(
                taskId=params.get("taskId", ""),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("FIND_OVERDUE_TASKS", "FINDOVERDUETASKS", "OVERDUE_TASKS"):
            res = await find_overdue_tasks(
                planName=params.get("planName"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("PREPARE_PLANNER_TASK", "PREPAREPLANNER"):
            res = await prepare_planner_task(
                planName=params.get("planName", params.get("planTitle", "Executive Strategic Initiatives")),
                bucketName=params.get("bucketName", "To do"),
                title=params.get("title", "Strategic Initiative Action Item"),
                description=params.get("description", params.get("notes", "")),
                assignees=params.get("assignees") or [params.get("assignedToEmail", email or "leadership@velora.ae")],
                dueDate=params.get("dueDate"),
                priority=params.get("priority", "High"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("CREATE_APPROVED_PLANNER_TASK", "CREATEAPPROVEDPLANNER"):
            res = await create_approved_planner_task(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("PREPARE_PLANNER_TASK_UPDATE", "PREPAREPLANNERUPDATE"):
            res = await prepare_planner_task_update(
                taskId=params.get("taskId", ""),
                updates=params.get("updates") or {
                    k: v for k, v in {
                        "title": params.get("title"),
                        "percentComplete": params.get("percentComplete"),
                        "dueDate": params.get("dueDate"),
                        "priority": params.get("priority"),
                        "description": params.get("notes"),
                    }.items() if v is not None
                },
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("UPDATE_APPROVED_PLANNER_TASK", "UPDATEAPPROVEDPLANNER"):
            res = await update_approved_planner_task(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("PREPARE_PLANNER_COMPLETION", "PREPAREPLANNERCOMPLETION"):
            res = await prepare_planner_completion(
                taskId=params.get("taskId", ""),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("COMPLETE_APPROVED_PLANNER_TASK", "COMPLETEAPPROVEDPLANNER"):
            res = await complete_approved_planner_task(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        else:
            return HandoffResponse(
                status="UNSUPPORTED_OPERATION",
                approvalRequired=False,
                resultSummary=f"Operation '{request.operation}' is not supported by Velora Productivity Agent.",
                correlationId=corr_id,
                auditStatus="ERROR",
                warnings=[f"Unknown operation {request.operation}"],
            )

    except Exception as ex:
        return HandoffResponse(
            status="ERROR",
            approvalRequired=False,
            resultSummary=f"Productivity Agent execution error: {str(ex)}",
            correlationId=corr_id,
            auditStatus="ERROR",
            warnings=[str(ex)],
        )


handle_handoff_request = handle_parent_handoff

