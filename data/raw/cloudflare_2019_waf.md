---
company: Cloudflare
date: 2019-07-02
component: WAF / Regex Engine
severity: Critical
duration_minutes: 27
---

# Cloudflare Global Network Outage (July 2019)

## Summary
On July 2, 2019, Cloudflare experienced a global outage lasting 27 minutes, resulting in 502 Bad Gateway errors across all edge locations worldwide. The incident was caused by a single misconfigured Web Application Firewall (WAF) rule deployed globally.

## Root Cause
An engineer deployed a new WAF managed rule intended to block inline JavaScript XSS attacks. The rule contained a poorly written regular expression ((?:(?:\"|'|\]|\}|\\|\d|(?:nan|infinity|true|false|null|undefined|symbol|math)|\|\-|\+)+[)]*;?((?:\s|-|~|!|{}|\|\||\+)*.*(?:.*=.*)))) that triggered catastrophic backtracking when evaluating specific HTTP payloads. This caused CPU utilization across all Cloudflare edge servers to spike to 100%, starving NGINX worker processes.

## Timeline
- 13:42 UTC: WAF rule update deployed globally without staged rollout.
- 13:45 UTC: Edge CPU utilization reached 100%; global HTTP 502 errors began.
- 14:00 UTC: Root cause isolated to the newly deployed WAF rule set.
- 14:09 UTC: Global WAF kill-switch activated; traffic recovered completely.

## Action Items
- Enforce mandatory staged rollouts (canary deployments) for all WAF rule updates.
- Implement static analysis and regex execution time benchmarks in the CI pipeline to prevent catastrophic backtracking.
- Add automated circuit breakers to disable rules if edge CPU exceeds threshold limits.
