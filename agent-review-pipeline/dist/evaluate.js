/**
 * Evaluate entry point — runs Stage B + C + scoring on Stage A output.
 *
 * Usage: node dist/evaluate.js --stage-a <path-to-stage-a.json> --dataverse-host <host>
 *
 * Expects environment variables: CLIENT_ID, TENANT_ID, CLIENT_SECRET
 * Outputs the full EvaluationResult JSON to stdout.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { parseArgs } from 'node:util';
import { runEvaluation } from './evaluation/evaluationOrchestrator.js';
import { generatePdfReport } from './report/pdfReport.js';
const { values } = parseArgs({
    options: {
        'stage-a': { type: 'string' },
        'dataverse-host': { type: 'string' },
        threshold: { type: 'string', default: '60' },
        output: { type: 'string' },
        'pdf-output': { type: 'string' },
    },
});
function parseThreshold(value) {
    const threshold = Number(value ?? '60');
    if (!Number.isInteger(threshold) || threshold < 0 || threshold > 100) {
        throw new Error(`Invalid threshold "${value}". Expected an integer from 0 to 100.`);
    }
    return threshold;
}
function validateDataverseHost(value) {
    const host = value.trim().toLowerCase();
    if (!/^[a-z0-9.-]+(?::\d{1,5})?$/.test(host) || host.includes('..')) {
        throw new Error('Invalid Dataverse host. Expected a hostname without a path or protocol.');
    }
    return host;
}
function writeResult(result) {
    const output = JSON.stringify(result, null, 2);
    if (values.output) {
        writeFileSync(values.output, output);
        console.error(`Evaluation result written to ${values.output}`);
    }
    else {
        console.log(output);
    }
}
if (!values['stage-a'] || !values['dataverse-host']) {
    console.error('Usage: node dist/evaluate.js --stage-a <path> --dataverse-host <host>');
    process.exit(1);
}
let threshold;
let dataverseHost;
try {
    threshold = parseThreshold(values.threshold);
    dataverseHost = validateDataverseHost(values['dataverse-host']);
}
catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
}
// Load and validate Stage A output before acquiring credentials or calling Dataverse.
const stageAJson = readFileSync(values['stage-a'], 'utf-8');
const parsed = JSON.parse(stageAJson);
const stageAOutputs = Array.isArray(parsed) ? parsed : [parsed];
const validOutputs = stageAOutputs.filter((output) => output && (output.topicComponents?.length || output.agentInstructions?.trim()));
if (validOutputs.length === 0) {
    const emptyResult = {
        agents: [],
        overall: { passed: false, lowestScore: 0, threshold, agentCount: 0 },
        scores: {
            passed: false,
            overallScore: 0,
            threshold,
            patternScore: 0,
            instructionScore: 0,
        },
        reportUrl: '',
        errors: ['No evaluatable agent content was found in the Stage A output'],
    };
    writeResult(emptyResult);
    process.exit(0);
}
const { CLIENT_ID, TENANT_ID, CLIENT_SECRET } = process.env;
if (!CLIENT_ID || !TENANT_ID || !CLIENT_SECRET) {
    console.error('Missing environment variables: CLIENT_ID, TENANT_ID, CLIENT_SECRET');
    process.exit(1);
}
// Acquire OAuth token for Dataverse
const tokenUrl = `https://login.microsoftonline.com/${encodeURIComponent(TENANT_ID)}/oauth2/v2.0/token`;
const tokenResponse = await fetch(tokenUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
        client_id: CLIENT_ID,
        scope: `https://${dataverseHost}/.default`,
        client_secret: CLIENT_SECRET,
        grant_type: 'client_credentials',
    }),
    signal: AbortSignal.timeout(30_000),
});
if (!tokenResponse.ok) {
    console.error(`OAuth token request failed: ${tokenResponse.status}`);
    process.exit(1);
}
const tokenData = (await tokenResponse.json());
if (!tokenData.access_token) {
    console.error('OAuth response missing access_token');
    process.exit(1);
}
// Run evaluation for each agent
const agentResults = [];
for (const stageAOutput of validOutputs) {
    console.log(`\n=== Evaluating: ${stageAOutput.botName} ===`);
    const result = await runEvaluation(dataverseHost, tokenData.access_token, stageAOutput, threshold);
    agentResults.push(result);
}
// Compute overall pass/fail (all agents must pass)
const lowestScore = Math.min(...agentResults.map((r) => r.scores.overallScore));
const allPassed = agentResults.every((r) => r.scores.passed);
// Build report URL from GitHub Actions environment
const reportUrl = process.env.GITHUB_SERVER_URL && process.env.GITHUB_REPOSITORY && process.env.GITHUB_RUN_ID
    ? `${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`
    : undefined;
const finalResult = {
    agents: agentResults,
    overall: {
        passed: allPassed,
        lowestScore,
        threshold,
        agentCount: agentResults.length,
    },
    // Backward-compatible: flow reads scores.passed / scores.overallScore
    scores: {
        passed: allPassed,
        overallScore: lowestScore,
        threshold,
        patternScore: agentResults.length === 1 ? agentResults[0].scores.patternScore : lowestScore,
        instructionScore: agentResults.length === 1 ? agentResults[0].scores.instructionScore : lowestScore,
    },
    // Link to the GitHub Actions run (includes downloadable PDF artifact)
    reportUrl: reportUrl ?? '',
};
// Output result
writeResult(finalResult);
// Generate PDF report
if (values['pdf-output']) {
    try {
        const pdfBuffer = generatePdfReport(agentResults);
        writeFileSync(values['pdf-output'], pdfBuffer);
        console.error(`PDF report written to ${values['pdf-output']}`);
    }
    catch (err) {
        console.error(`PDF generation failed: ${err instanceof Error ? err.message : err}`);
    }
}
