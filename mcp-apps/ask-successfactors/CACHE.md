# MCP caching

Both SAP MCP servers include an optional, bounded in-process cache for successful read requests. It reduces repeated SAP calls and coalesces simultaneous identical requests while preserving the source, freshness, authorization, and audit information that the Copilot response needs.

## Defaults

| Server | Default TTL | Default entries | Additional cache |
|---|---:|---:|---|
| SuccessFactors OData pages | 120 seconds | 512 | Successful writes clear all local HCM entries |
| SuccessFactors aggregates | 900 seconds | 128 | Headcount and joiner results; permission/filter/date scoped |
| S/4HANA | 60 seconds | 512 | OAuth access token reused until 30 seconds before expiry |

Set `CACHE_ENABLED=false` to bypass result caching. `CACHE_TTL_SECONDS=0` or `CACHE_MAX_ENTRIES=0` also disables it. Tune `CACHE_TTL_SECONDS` and `CACHE_MAX_ENTRIES` independently for each deployment. `OAUTH_TOKEN_CACHE_SKEW_SECONDS` applies only to S/4HANA OAuth authentication.

For SuccessFactors, `AGGREGATE_CACHE_TTL_SECONDS` and `AGGREGATE_CACHE_MAX_ENTRIES` control the whole-result cache used by expensive paginated headcount and new-hire aggregations. The deployed recommendation is 15 minutes, while underlying OData pages remain cached for two minutes.

## Correctness and isolation

- Only successful reads are cached. SAP errors, timeouts, authorization failures, and malformed results are never stored.
- The SuccessFactors key contains the effective executive identity, endpoint, base URL, and every normalized OData parameter.
- The S/4HANA key contains the configured authorization mode, entity, base URL, and every normalized OData parameter. This server uses one scoped SAP identity per deployment.
- Values are copied on both insertion and retrieval so one request cannot mutate another request's result.
- Simultaneous identical misses share one upstream request.
- Every result includes `cache.status`, `cache.ageSeconds`, `cache.ttlSeconds`, and `cache.storedAt`. S/4HANA `source.asOf` remains the original cache storage time on a hit.
- No cache key or diagnostic metadata contains SAP passwords, OAuth tokens, MCP API keys, or record payloads.

Statuses are `disabled`, `miss`, `hit`, and `coalesced`. The agent should use cached data normally when it remains inside the configured TTL, while stating the supplied source freshness when material to the decision.

## Deployment considerations

The cache is intentionally local to each MCP process. It requires no additional data store and does not move SAP data outside that process. With multiple application instances, each instance maintains an independent bounded cache; use consistent TTL configuration and expect the first request on each instance to reach SAP.

Choose TTLs with the HR and finance data owners. Lower the TTL for volatile operational values, or disable caching for an incident requiring immediate source reads. Do not use a long TTL as a substitute for SAP availability or precompute data beyond the user's authorized scope.
