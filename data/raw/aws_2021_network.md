---
company: AWS
date: 2021-12-07
component: Internal Network / Control Plane
severity: High
duration_minutes: 450
---

# AWS US-EAST-1 Network Congestion Event (December 2021)

## Summary
On December 7, 2021, AWS experienced a 7.5-hour service disruption in the US-EAST-1 (Northern Virginia) region affecting EC2, DynamoDB, Lambda, and IAM control planes due to severe internal network congestion.

## Root Cause
An automated scaling activity triggered a surge of connection requests from client services hosted on the main AWS network to internal state-tracking services hosted on an isolated internal network. This sudden traffic spike overwhelmed the intermediate network devices bridging the two networks. The resulting packet loss caused clients to aggressively retry failed connections, creating a self-sustaining retry storm that saturated link capacity and prevented DNS resolution for internal service endpoints.

## Timeline
- 15:30 UTC: Automated scaling event initiated high volume of state-service requests.
- 15:45 UTC: Packet loss detected on border network devices; retry storms escalated congestion.
- 18:10 UTC: Engineers identified the traffic source and began throttling scaling workflows.
- 22:55 UTC: Network congestion cleared and all AWS control plane APIs returned to normal latency.

## Action Items
- Implement adaptive backoff and jitter across all internal service clients to prevent retry storms.
- Add strict rate limiting and circuit breaking on border routers connecting the main and internal networks.
- Decouple critical control-plane health checks from congested internal DNS resolution paths.
