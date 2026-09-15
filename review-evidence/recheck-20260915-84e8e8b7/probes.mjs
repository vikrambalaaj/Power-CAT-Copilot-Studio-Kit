import fs from 'node:fs';
import { IdempotencySigner } from '../../mcp-apps/dynamic-adaptive-card-service/dist/security/idempotency-signer.js';
import { calculateScores } from '../../agent-review-pipeline/dist/evaluation/scoreCalculator.js';

const signer = new IdempotencySigner('synthetic-review-key');
const { ticketToken } = signer.generateTicket('synthetic-session', 'approval-card');
const result = {
  cardReplay: {
    first: signer.verifyAndConsumeTicket(ticketToken).valid,
    exactReplay: signer.verifyAndConsumeTicket(ticketToken).valid,
    appendedSegmentReplay: signer.verifyAndConsumeTicket(ticketToken + '.extra').valid,
    secondAppendedSegmentReplay: signer.verifyAndConsumeTicket(ticketToken + '.another').valid,
    freshInstanceReplay: new IdempotencySigner('synthetic-review-key').verifyAndConsumeTicket(ticketToken).valid,
  },
  missingStageB: calculateScores(undefined, { issues: [] }),
  missingStageC: calculateScores({ Patterns: [{ Status: true }] }, undefined),
};
fs.writeFileSync(new URL('./node-probes.json', import.meta.url), JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
