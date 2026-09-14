"""Test One-Time Enterprise Consent Gating and Time-Aware Greeting Flow."""
import asyncio
import pytest
from successfactors_mcp.successfactors_tools import (
    sf__check_and_record_consent,
    sf__get_session_greeting,
)
from successfactors_mcp.greeting_service import (
    get_time_aware_salutation,
    build_capabilities_card,
)


@pytest.mark.asyncio
async def test_one_time_consent_and_greeting_lifecycle():
    test_user_email = "executive.test@velora.ae"
    test_user_oid = "usr-test-oid-999"

    import json

    def extract_res(res):
        if hasattr(res, "structuredContent") and res.structuredContent:
            return res.structuredContent
        elif hasattr(res, "content") and res.content:
            return json.loads(res.content[0].text)
        return res

    initial_check_raw = await sf__check_and_record_consent(
        user_object_id=test_user_oid,
        user_email=test_user_email,
        action="check",
    )
    initial_check = extract_res(initial_check_raw)
    
    assert initial_check["type"] == "ConsentCheck"
    assert initial_check["is_consented"] is False
    assert initial_check["adaptiveCard"] is not None
    assert initial_check["adaptiveCard"]["type"] == "AdaptiveCard"
    
    # Check that Adaptive Card has the Input.Toggle checkbox
    card_body = initial_check["adaptiveCard"]["body"]
    checkbox = next((item for item in card_body if item.get("type") == "Input.Toggle"), None)
    assert checkbox is not None
    assert checkbox["id"] == "consent_agreement"
    assert checkbox["isRequired"] is True
    print("✓ Step 1 Passed: Consent check successfully returned Adaptive Card with checkbox for new user.")

    # Step 2: User checks box and accepts consent
    record_result_raw = await sf__check_and_record_consent(
        user_object_id=test_user_oid,
        user_email=test_user_email,
        action="record",
        accepted=True,
    )
    record_result = extract_res(record_result_raw)
    print("Record result payload:", record_result)
    assert record_result["type"] == "ConsentRecorded"
    assert record_result["consent_status"] == "ACCEPTED"
    print("✓ Step 2 Passed: User consent acceptance recorded to Dataverse audit store.")

    # Step 3: Subsequent session / turn - User consent is now active
    subsequent_check_raw = await sf__check_and_record_consent(
        user_object_id=test_user_oid,
        user_email=test_user_email,
        action="check",
    )
    subsequent_check = extract_res(subsequent_check_raw)
    assert subsequent_check["type"] == "ConsentCheck"
    assert subsequent_check["is_consented"] is True
    assert subsequent_check["adaptiveCard"] is None
    print("✓ Step 3 Passed: Subsequent session verified active consent (card suppressed).")

    # Step 4: Greeting service returns time-based greeting for consented user
    greeting_res_raw = await sf__get_session_greeting(
        user_object_id=test_user_oid,
        user_email=test_user_email,
        user_display_name="Bala Admin",
        user_timezone="Asia/Dubai",
    )
    greeting_res = extract_res(greeting_res_raw)
    assert greeting_res["type"] == "SessionGreeting"
    assert greeting_res["is_consented"] is True
    assert greeting_res["salutation"] in {
        "Welcome",
        "Good morning",
        "Good afternoon",
        "Good evening",
    }
    assert "Bala" in greeting_res["fallback_text"]
    print(f"✓ Step 4 Passed: Time-based greeting generated: '{greeting_res['salutation']}' for '{greeting_res['user_display_name']}'.")


if __name__ == "__main__":
    asyncio.run(test_one_time_consent_and_greeting_lifecycle())
