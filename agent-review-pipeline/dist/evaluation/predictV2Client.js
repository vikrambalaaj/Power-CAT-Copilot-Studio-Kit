/**
 * PredictV2 Client — calls AI Builder custom prompts via Dataverse unbound action.
 *
 * Uses the same SPN OAuth token already acquired for artifact download.
 */
import { AI_MODEL_IDS, COMPLIANCE_CRITERIA } from './constants.js';
const REQUEST_TIMEOUT_MS = 60_000;
const MAX_ERROR_BODY_LENGTH = 1_000;
function parseModelJson(text, label) {
    const trimmed = text.trim();
    const withoutFence = trimmed.startsWith('```')
        ? trimmed.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '')
        : trimmed;
    try {
        return JSON.parse(withoutFence);
    }
    catch {
        throw new Error(`${label} returned malformed JSON`);
    }
}
/**
 * Validate an individual pattern record returned by Stage B.
 */
export function validatePattern(p) {
    if (!p || typeof p !== 'object') {
        throw new Error('Pattern item must be a non-null object');
    }
    const item = p;
    if (typeof item.PatternName !== 'string' || item.PatternName.trim().length === 0) {
        throw new Error(`Stage B pattern is missing a valid PatternName: ${JSON.stringify(p)}`);
    }
    if (typeof item.Status !== 'boolean') {
        throw new Error(`Stage B pattern "${item.PatternName}" Status must be a boolean, got ${typeof item.Status}`);
    }
    return true;
}
/**
 * Validate an individual compliance issue returned by Stage C.
 */
export function validateIssue(i) {
    if (!i || typeof i !== 'object') {
        throw new Error('Issue item must be a non-null object');
    }
    const item = i;
    if (typeof item.id !== 'string' || item.id.trim().length === 0) {
        throw new Error(`Stage C issue is missing a valid id: ${JSON.stringify(i)}`);
    }
    const id = item.id.trim();
    const isValidCriterion = id === 'missing-instruction-input' ||
        COMPLIANCE_CRITERIA.some((c) => id === c.id || id.startsWith(c.id));
    if (!isValidCriterion) {
        throw new Error(`Stage C issue contains unknown criterion ID: "${id}"`);
    }
    if (item.severity && !['High', 'Medium', 'Low'].includes(String(item.severity))) {
        throw new Error(`Stage C issue "${id}" has invalid severity: "${item.severity}"`);
    }
    return true;
}
/**
 * Call AI Builder PredictV2 unbound action on Dataverse.
 *
 * Endpoint: POST https://<dataverseHost>/api/data/v9.2/PredictV2
 *
 * Payload:
 * {
 *   "predictionName": "<AI_MODEL_ID>",
 *   "operationType": "ExecutePrompt",
 *   "predictionInput": { ...parameters }
 * }
 */
async function callPredictV2(dataverseHost, accessToken, predictionName, predictionInput) {
    const url = `https://${dataverseHost}/api/data/v9.2/PredictV2`;
    const payload = {
        predictionName,
        operationType: 'ExecutePrompt',
        predictionInput,
    };
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
            Accept: 'application/json',
        },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (!response.ok) {
        const errorBody = await response.text().catch(() => '');
        const truncated = errorBody.slice(0, MAX_ERROR_BODY_LENGTH);
        throw new Error(`PredictV2 HTTP ${response.status} for model ${predictionName}: ${truncated}`);
    }
    const data = (await response.json());
    const textOutput = data.responsev2?.predictionOutput?.text;
    if (!textOutput) {
        throw new Error('PredictV2 returned no text output');
    }
    return textOutput;
}
/**
 * Invoke Stage B: Pattern Evaluation
 *
 * @param dataverseHost - Dataverse host (e.g., org.crm.dynamics.com)
 * @param accessToken - OAuth Bearer token
 * @param botComponentsJson - Stage A output stringified (topicComponents)
 */
export async function invokeStageB(dataverseHost, accessToken, botComponentsJson) {
    const textOutput = await callPredictV2(dataverseHost, accessToken, AI_MODEL_IDS.STAGE_B_PATTERN_EVAL, { botcomponents: botComponentsJson });
    const evaluation = parseModelJson(textOutput, 'Stage B');
    if (!Array.isArray(evaluation.Patterns)) {
        throw new Error('Stage B response is missing the Patterns array');
    }
    for (const p of evaluation.Patterns) {
        validatePattern(p);
    }
    return evaluation;
}
/**
 * Invoke Stage C: Instruction Compliance
 *
 * @param dataverseHost - Dataverse host (e.g., org.crm.dynamics.com)
 * @param accessToken - OAuth Bearer token
 * @param agentInstructions - Raw agent instructions text
 */
export async function invokeStageC(dataverseHost, accessToken, agentInstructions) {
    const textOutput = await callPredictV2(dataverseHost, accessToken, AI_MODEL_IDS.STAGE_C_COMPLIANCE, { Instruction_20Input: agentInstructions });
    const evaluation = parseModelJson(textOutput, 'Stage C');
    if (!Array.isArray(evaluation.issues)) {
        throw new Error('Stage C response is missing the issues array');
    }
    for (const issue of evaluation.issues) {
        validateIssue(issue);
    }
    return evaluation;
}
