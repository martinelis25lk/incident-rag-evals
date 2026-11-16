---
company: GitLab
date: 2017-01-31
component: PostgreSQL / Database
severity: Critical
duration_minutes: 1080
---

# GitLab.com Production Database Outage (January 2017)

## Summary
On January 31, 2017, GitLab.com suffered an 18-hour outage accompanied by the permanent loss of approximately 6 hours of production database data (issues, merge requests, and comments) after an engineer accidentally deleted the primary PostgreSQL data directory.

## Root Cause
Following an aggressive spam attack that overloaded the database, replication lag between the primary PostgreSQL node (db1) and the secondary replica (db2) grew beyond 4 GB, breaking replication. While attempting to clear the stale PostgreSQL data directory on db2 to resynchronize replication, an on-call engineer mistakenly executed m -rf /var/opt/gitlab/postgresql/data on the primary server (db1) instead of the replica. Subsequent investigation revealed that all five automated backup mechanisms (pg_dump, LVM snapshots, S3 sync) had silently failed due to configuration mismatches and PostgreSQL version incompatibilities.

## Timeline
- 17:20 UTC: Heavy database load caused replication lag to exceed threshold; replica dropped out of sync.
- 23:00 UTC: Engineer wiped the pgdata directory on db1 by mistake, deleting ~300 GB of live data.
- 23:15 UTC: Backup audit revealed pg_dump was failing silently due to binary version mismatch (9.2 vs 9.6).
- 03:30 UTC (Feb 1): Recovery initiated from a 6-hour-old LVM snapshot taken manually before maintenance.

## Action Items
- Configure distinct terminal prompts and color-coded SSH banners to differentiate primary and replica database hosts.
- Implement continuous automated backup restoration testing and alerting on zero-byte backup artifacts.
- Migrate database replication management to automated failover tooling (Patroni) to eliminate manual directory manipulation.
