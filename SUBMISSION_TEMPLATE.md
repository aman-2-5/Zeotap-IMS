# Aman Lodha - Infrastructure / SRE Intern Assignment

## **Candidate**
- **Name:** Aman Lodha
- **Role:** Infrastructure / SRE Intern

## **GitHub Repository**
- **Repository Link:** `(https://github.com/aman-2-5/Zeotap-IMS)`

## **Problem Statement**
Built a resilient Incident Management System (IMS) for high-volume distributed-system failure signals. The system ingests, debounces, persists, alerts, and tracks incidents through to closure with mandatory RCA and MTTR computation.

## **Architecture**
- Async ingestion API with rate limiting and backpressure.
- In-memory bounded queue to absorb bursts and decouple ingestion from sink speed.
- MongoDB sink for raw signal payloads and work-item signal linkage.
- PostgreSQL transactional sink for work items, RCA records, and aggregation rows.
- Redis hot-path cache for dashboard state and debounce keying.
- Strategy Pattern for alert routing by severity.
- State Pattern for incident lifecycle transitions and RCA-guarded closure.
- Frontend dashboard to view incidents, inspect raw signals, update status, and submit RCA.

## **Functional Coverage**
- Supports async processing.
- Rejects `CLOSED` transition when RCA missing/incomplete.
- Calculates MTTR automatically from incident start/end.
- Live incident feed sorted by severity.
- Incident detail view includes raw NoSQL signals.
- RCA form includes all mandatory fields.

## **Resilience & Performance**
- Rate limiter on ingestion endpoint to prevent cascading failures.
- Backpressure via bounded queue and fail-fast `503` behavior.
- Retry logic for persistence failures in worker.
- `/health` endpoint with sink health checks.
- Throughput metric logging (`signals/sec`) every 5 seconds.

## **Testing**
- Unit tests implemented for workflow RCA validation.
- Test command: `python -m pytest -q`

## **Run Instructions**
1. `docker compose up --build`
2. Open dashboard at `http://localhost:8081`
3. API health at `http://localhost:8000/health`
4. Simulate failures with: `python scripts/simulate_signals.py`

## **Additional Notes**
- Included `PROMPTS_AND_PLAN.md` to capture prompts/spec/planning artifacts.
- Included sample failure data in `sample_signals.json`.

## **Submission Checklist**
- [ ] Repository pushed to GitHub.
- [ ] Repository Link field updated with the exact GitHub URL.
- [ ] File exported as PDF named: `Aman Lodha - Infrastructure / SRE Intern Assignment.pdf`
