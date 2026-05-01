# Prompts, Plan, and Execution Notes

## Prompt Intent
Build a resilient incident management system with:
- async ingestion
- burst handling and backpressure
- debouncing by component
- NoSQL raw signal sink
- transactional source of truth for incidents + RCA
- hot-path dashboard cache
- aggregation sink
- strategy + state patterns
- responsive dashboard

## Implementation Plan
1. Build backend with FastAPI and async queue.
2. Add PostgreSQL for structured transactional entities.
3. Add MongoDB for raw signal payloads and work-item-linked signal logs.
4. Add Redis for debounce keys and dashboard hot state.
5. Implement strategy pattern for alert dispatch selection.
6. Implement state pattern for incident workflow transitions with RCA enforcement.
7. Create frontend dashboard to list, inspect, update, and add RCA.
8. Package with Docker Compose and provide sample load script.
9. Add unit tests for RCA closure validation.

## Backpressure Strategy
- `POST /ingest` enqueues into bounded `asyncio.Queue`.
- When queue fills, API returns `503` quickly (fail-fast, protects process memory).
- Worker retries failed persistence with delayed requeue.
- In-memory queue decouples ingress from sink slowdowns.
