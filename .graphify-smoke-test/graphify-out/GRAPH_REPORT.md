# Graph Report - .graphify-smoke-test  (2026-08-28)

## Corpus Check
- 2 files · ~28 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 4 nodes · 5 edges · 1 communities (0 shown, 1 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `5d8ce0ce`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- app.js

## God Nodes (most connected - your core abstractions)
1. `loadCustomer()` - 3 edges
2. `customerSummary()` - 2 edges

## Surprising Connections (you probably didn't know these)
- `customerSummary()` --calls--> `loadCustomer()`  [EXTRACTED]
  app.js → service.js

## Import Cycles
- None detected.

## Communities (1 total, 1 thin omitted)

## Knowledge Gaps
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Not enough signal to generate questions. This usually means the corpus has no AMBIGUOUS edges, no bridge nodes, no INFERRED relationships, and all communities are tightly cohesive. Add more files or run with --mode deep to extract richer edges._