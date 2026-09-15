/**
 * Score Calculator — deterministic scoring logic for agent reviews.
 *
 * Ported from CopilotStudioKit/src/features/agent-review-tool/utils/scoreCalculator.ts
 */

import {
  COMPLIANCE_CRITERIA,
  SEVERITY_POINTS,
  MAX_INSTRUCTION_POINTS,
  DEFAULT_THRESHOLD,
} from './constants.js';
import type { PatternEvaluation, InstructionEvaluation } from './predictV2Client.js';

/** Final score result returned in the callback payload */
export interface ScoreResult {
  patternScore: number;
  instructionScore: number;
  overallScore: number;
  passed: boolean;
  threshold: number;
  stageBPatternCount: number;
  stageBPassingCount: number;
  stageCIssueCount: number;
}

/**
 * Calculate pattern score from Stage B output.
 * Formula: (passing / total) × 100
 */
export function calculatePatternScore(evaluation?: PatternEvaluation): number {
  if (!evaluation?.Patterns?.length) return 0;
  const total = evaluation.Patterns.length;
  const passing = evaluation.Patterns.filter((p) => p.Status === true).length;
  return Math.round((passing / total) * 100);
}

/**
 * Calculate instruction compliance score from Stage C output.
 * Uses severity-weighted scoring (High=3, Medium=2, Low=1).
 * A criterion passes if no issue ID starts with its prefix.
 */
export function calculateInstructionScore(evaluation?: InstructionEvaluation): number {
  if (!evaluation?.issues) return 0;

  // Missing instructions = all criteria fail = 0%
  if (evaluation.issues.some((i) => i.id === 'missing-instruction-input')) return 0;

  const issueIds = evaluation.issues.map((i) => i.id);

  const earnedPoints = COMPLIANCE_CRITERIA.reduce((sum, criterion) => {
    const failed = issueIds.some((id) => id.startsWith(criterion.id));
    return failed ? sum : sum + SEVERITY_POINTS[criterion.inherentSeverity];
  }, 0);

  return Math.round((earnedPoints / MAX_INSTRUCTION_POINTS) * 100);
}

export interface ScoreCalculationOptions {
  stageBCompleted?: boolean;
  stageCCompleted?: boolean;
  hasErrors?: boolean;
}

/**
 * Calculate overall score and determine pass/fail.
 *
 * Formula: (patternScore × 0.5) + (instructionScore × 0.5)
 * All mandatory stages (Stage B and Stage C) must complete successfully.
 * A missing, failed, or incomplete stage causes the evaluation gate to fail.
 * Stage errors prevent release pass.
 */
export function calculateScores(
  stageBResult?: PatternEvaluation,
  stageCResult?: InstructionEvaluation,
  threshold: number = DEFAULT_THRESHOLD,
  options?: ScoreCalculationOptions
): ScoreResult {
  const patternScore = calculatePatternScore(stageBResult);
  const instructionScore = calculateInstructionScore(stageCResult);

  const stageBCompleted =
    options?.stageBCompleted !== undefined
      ? options.stageBCompleted
      : Boolean(stageBResult && Array.isArray(stageBResult.Patterns) && stageBResult.Patterns.length > 0);
  const stageCCompleted =
    options?.stageCCompleted !== undefined
      ? options.stageCCompleted
      : Boolean(stageCResult && Array.isArray(stageCResult.issues));
  const hasErrors = options?.hasErrors ?? false;

  const isComplete = stageBCompleted && stageCCompleted && !hasErrors;

  const overallScore = Math.round(patternScore * 0.5 + instructionScore * 0.5);
  const passed = isComplete && overallScore >= threshold;

  return {
    patternScore,
    instructionScore,
    overallScore,
    passed,
    threshold,
    stageBPatternCount: stageBResult?.Patterns?.length ?? 0,
    stageBPassingCount: stageBResult?.Patterns?.filter((p) => p.Status === true).length ?? 0,
    stageCIssueCount: stageCResult?.issues?.length ?? 0,
  };
}

