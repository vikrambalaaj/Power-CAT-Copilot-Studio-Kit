import assert from 'node:assert/strict';
import test from 'node:test';
import {
  calculateInstructionScore,
  calculatePatternScore,
  calculateScores,
} from '../dist/evaluation/scoreCalculator.js';

test('pattern score counts only explicitly passing patterns', () => {
  assert.equal(calculatePatternScore({
    Patterns: [
      { PatternName: 'pass', Status: true },
      { PatternName: 'fail', Status: false },
      { PatternName: 'invalid' },
    ],
  }), 33);
});

test('missing instruction input always scores zero', () => {
  assert.equal(calculateInstructionScore({
    compliancePercentage: 100,
    issues: [{
      id: 'missing-instruction-input',
      title: 'Missing instructions',
      severity: 'High',
      description: 'No instructions were supplied',
    }],
  }), 0);
});

test('overall score uses the available stage when the other stage fails', () => {
  const result = calculateScores({ Patterns: [{ PatternName: 'pass', Status: true }] }, undefined, 60);
  assert.equal(result.overallScore, 100);
  assert.equal(result.passed, true);
});
