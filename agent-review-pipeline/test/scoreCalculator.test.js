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

test('overall evaluation gate fails when a mandatory stage is missing', () => {
  const result = calculateScores({ Patterns: [{ PatternName: 'pass', Status: true }] }, undefined, 60);
  assert.equal(result.overallScore, 50);
  assert.equal(result.passed, false);
});

test('nameless pattern causes pattern score to return zero', () => {
  assert.equal(calculatePatternScore({
    Patterns: [
      { Status: true },
    ],
  }), 0);
});

test('unknown issue ID causes instruction score to return zero', () => {
  assert.equal(calculateInstructionScore({
    compliancePercentage: 100,
    issues: [{
      id: 'unknown-criterion',
      title: 'Unknown issue',
      severity: 'High',
      description: 'Not in known criteria',
    }],
  }), 0);
});

