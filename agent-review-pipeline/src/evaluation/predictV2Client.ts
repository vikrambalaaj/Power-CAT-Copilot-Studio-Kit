/**
 * PredictV2 Client — calls AI Builder custom prompts via Dataverse unbound action.
 *
 * Uses the same SPN OAuth token already acquired for artifact download.
 */

import { AI_MODEL_IDS } from './constants.js';

/** Stage B response: list of patterns with pass/fail status */
export interface PatternEvaluation {
  Patterns: Array<{
    PatternName: string;
    Status: boolean;
    Category?: string;
    Severity?: string;
    Recommendation?: string;
    /** Affected topics — AI returns as {item: string}[], local patterns as string[] */
    Topics?: Array<{ item: string }> | string[];
  }>;
  PatternCompliancePercentage?: number;
}

/** Stage C response: instruction compliance issues */
export interface InstructionEvaluation {
  compliancePercentage: number;
  issues: Array<{
    id: string;
    title: string;
    severity: string;
    description: string;
  }>;
}

/** PredictV2 API response shape */
interface PredictV2Response {
  responsev2?: {
    predictionOutput?: {
      text?: string;
    };
  };
}

const REQUEST_TIMEOUT_MS = 60_000;
const MAX_ERROR_BODY_LENGTH = 1_000;

function parseModelJson<T>(text: string, label: string): T {
  const trimmed = text.trim();
  const withoutFence = trimmed.startsWith('```')
    ? trimmed.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '')
    : trimmed;

  try {
    return JSON.parse(withoutFence) as T;
  } catch {
    throw new Error(`${label} returned malformed JSON`);
  }
}

/**
 * Call AI Builder PredictV2 unbound action on Dataverse.
 */
async function callPredictV2(
  dataverseHost: string,
  accessToken: string,
  modelId: string,
  requestv2: Record<string, unknown>
): Promise<string> {
  const url = `https://${dataverseHost}/api/data/v9.2/msdyn_aimodels(${modelId})/Microsoft.Dynamics.CRM.Predict`;

  const body = {
    version: '2.0',
    source: JSON.stringify({
      consumptionSource: 'Api',
      partnerSource: 'PVA',
      consumptionSourceVersion: 'GptApiClient',
    }),
    requestv2: {
      '@odata.type': '#Microsoft.Dynamics.CRM.expando',
      ...requestv2,
      $customConfig: {
        '@odata.type': '#Microsoft.Dynamics.CRM.expando',
        settings: {
          '@odata.type': '#Microsoft.Dynamics.CRM.expando',
          runtime: null,
        },
      },
    },
  };

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
      'OData-MaxVersion': '4.0',
      'OData-Version': '4.0',
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });

  if (!response.ok) {
    const errorText = (await response.text()).slice(0, MAX_ERROR_BODY_LENGTH);
    throw new Error(`PredictV2 failed (${response.status}): ${errorText}`);
  }

  const result = (await response.json()) as PredictV2Response;
  const textOutput = result.responsev2?.predictionOutput?.text;

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
export async function invokeStageB(
  dataverseHost: string,
  accessToken: string,
  botComponentsJson: string
): Promise<PatternEvaluation> {
  const textOutput = await callPredictV2(
    dataverseHost,
    accessToken,
    AI_MODEL_IDS.STAGE_B_PATTERN_EVAL,
    { botcomponents: botComponentsJson }
  );

  const evaluation = parseModelJson<PatternEvaluation>(textOutput, 'Stage B');
  if (!Array.isArray(evaluation.Patterns)) {
    throw new Error('Stage B response is missing the Patterns array');
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
export async function invokeStageC(
  dataverseHost: string,
  accessToken: string,
  agentInstructions: string
): Promise<InstructionEvaluation> {
  const textOutput = await callPredictV2(
    dataverseHost,
    accessToken,
    AI_MODEL_IDS.STAGE_C_COMPLIANCE,
    { Instruction_20Input: agentInstructions }
  );

  const evaluation = parseModelJson<InstructionEvaluation>(textOutput, 'Stage C');
  if (!Array.isArray(evaluation.issues)) {
    throw new Error('Stage C response is missing the issues array');
  }
  return evaluation;
}
