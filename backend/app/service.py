import asyncio
from collections import defaultdict
from datetime import UTC, datetime

from dateutil import parser
from redis.asyncio import Redis
from sqlalchemy import desc, select

from app.alerting import AlertStrategyFactory
from app.db import IncidentAggregation, RCARecord, SessionLocal, WorkItem
from app.schemas import RCAIn, Severity, SignalIn, WorkItemStatus


class IncidentService:
    def __init__(self, mongo_db, redis_client: Redis):
        self.mongo_db = mongo_db
        self.redis_client = redis_client
        self.ingested_since_last_log = 0
        self.component_priorities = {
            "RDBMS": Severity.P0,
            "NOSQL": Severity.P1,
            "CACHE": Severity.P2,
            "QUEUE": Severity.P1,
            "API": Severity.P2,
            "MCP": Severity.P1,
            "DEFAULT": Severity.P3,
        }
        self.signal_count_for_work_item = defaultdict(int)

    def compute_severity(self, component_type: str) -> Severity:
        key = component_type.upper()
        return self.component_priorities.get(key, self.component_priorities["DEFAULT"])

    async def record_signal(self, signal: SignalIn) -> None:
        self.ingested_since_last_log += 1
        signal_doc = signal.model_dump(mode="json")
        signal_doc["received_at"] = datetime.now(tz=UTC)
        await self.mongo_db.raw_signals.insert_one(signal_doc)
        await self._debounced_work_item(signal, signal_doc)

    async def _debounced_work_item(self, signal: SignalIn, signal_doc: dict) -> None:
        now = datetime.now(tz=UTC)
        debounce_key = f"debounce:{signal.component_id}"
        from app.settings import settings

        window = settings.debounce_window_seconds
        existing_id = await self.redis_client.get(debounce_key)
        work_item_id = int(existing_id) if (existing_id and existing_id.isdigit()) else None

        async with SessionLocal() as session:
            if work_item_id is None:
                # Atomic debounce for concurrent workers:
                # 1) Try to acquire creation token using NX.
                # 2) Winner creates WorkItem and replaces token with the id.
                # 3) Losers wait briefly for token to become the id.
                acquired = await self.redis_client.set(debounce_key, "PENDING", nx=True, ex=window)
                if not acquired:
                    for _ in range(8):  # <= ~200ms total
                        await asyncio.sleep(0.025)
                        v = await self.redis_client.get(debounce_key)
                        if v and v != "PENDING" and v.isdigit():
                            work_item_id = int(v)
                            break

                if work_item_id is None and acquired:
                    severity = self.compute_severity(signal.component_type)
                    item = WorkItem(
                        component_id=signal.component_id,
                        component_type=signal.component_type,
                        severity=severity.value,
                        status=WorkItemStatus.OPEN.value,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(item)
                    await session.flush()
                    work_item_id = item.id
                    await self.redis_client.setex(debounce_key, window, str(work_item_id))

                    alert_message = f"{signal.component_type} failure for {signal.component_id}"
                    strategy = AlertStrategyFactory.for_severity(severity)
                    rendered_alert = await strategy.alert(signal.component_id, alert_message)
                    print(rendered_alert, flush=True)

                if work_item_id is None:
                    # Fallback: if we couldn't get the id from Redis (rare),
                    # query the most recent WorkItem for this component.
                    stmt = (
                        select(WorkItem)
                        .where(WorkItem.component_id == signal.component_id)
                        .order_by(WorkItem.created_at.desc())
                        .limit(1)
                    )
                    row = (await session.execute(stmt)).scalar_one_or_none()
                    if row is None:
                        raise RuntimeError("Debounce failed: no work item created")
                    work_item_id = row.id

            self.signal_count_for_work_item[work_item_id] += 1
            signal_doc["work_item_id"] = work_item_id
            await self.mongo_db.work_item_signals.insert_one(signal_doc)
            await self._update_cache_and_aggregations(session, signal, work_item_id)
            await session.commit()

    async def _update_cache_and_aggregations(self, session, signal: SignalIn, work_item_id: int) -> None:
        bucket = datetime.now(tz=UTC).replace(second=0, microsecond=0)
        severity = self.compute_severity(signal.component_type).value
        stmt = select(IncidentAggregation).where(
            IncidentAggregation.bucket_start == bucket,
            IncidentAggregation.component_type == signal.component_type,
            IncidentAggregation.severity == severity,
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = IncidentAggregation(
                bucket_start=bucket, component_type=signal.component_type, severity=severity, count=1
            )
            session.add(row)
        else:
            row.count += 1

        dashboard_key = f"dashboard:item:{work_item_id}"
        await self.redis_client.hset(
            dashboard_key,
            mapping={
                "work_item_id": work_item_id,
                "component_id": signal.component_id,
                "component_type": signal.component_type,
                "severity": severity,
                "signals": self.signal_count_for_work_item[work_item_id],
                "updated_at": datetime.now(tz=UTC).isoformat(),
            },
        )
        await self.redis_client.expire(dashboard_key, 600)

    async def create_or_update_rca(self, work_item_id: int, rca: RCAIn) -> dict:
        mttr_minutes = (rca.incident_end - rca.incident_start).total_seconds() / 60
        if mttr_minutes < 0:
            raise ValueError("Incident end must be greater than start")

        now = datetime.now(tz=UTC)
        async with SessionLocal() as session:
            existing = (
                await session.execute(select(RCARecord).where(RCARecord.work_item_id == work_item_id))
            ).scalar_one_or_none()

            if existing is None:
                existing = RCARecord(
                    work_item_id=work_item_id,
                    incident_start=rca.incident_start,
                    incident_end=rca.incident_end,
                    root_cause_category=rca.root_cause_category,
                    fix_applied=rca.fix_applied,
                    prevention_steps=rca.prevention_steps,
                    mttr_minutes=mttr_minutes,
                    created_at=now,
                )
                session.add(existing)
            else:
                existing.incident_start = rca.incident_start
                existing.incident_end = rca.incident_end
                existing.root_cause_category = rca.root_cause_category
                existing.fix_applied = rca.fix_applied
                existing.prevention_steps = rca.prevention_steps
                existing.mttr_minutes = mttr_minutes
            await session.commit()
            return {"work_item_id": work_item_id, "mttr_minutes": round(mttr_minutes, 2)}

    async def list_active_incidents(
        self, include_closed: bool = False, only_closed: bool = False
    ) -> list[dict]:
        severity_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

        async with SessionLocal() as session:
            stmt = select(WorkItem)
            if only_closed:
                stmt = stmt.where(WorkItem.status == WorkItemStatus.CLOSED.value)
            elif not include_closed:
                stmt = stmt.where(WorkItem.status != WorkItemStatus.CLOSED.value)

            rows = (await session.execute(stmt)).scalars().all()

            result = []
            for row in rows:
                count = self.signal_count_for_work_item[row.id]
                result.append(
                    {
                        "id": row.id,
                        "component_id": row.component_id,
                        "component_type": row.component_type,
                        "severity": row.severity,
                        "status": row.status,
                        "signal_count": count,
                        "updated_at": row.updated_at,
                    }
                )

            # P0 highest priority, then newest updated
            result.sort(
                key=lambda x: (severity_order.get(x["severity"], 99), x["updated_at"]),
                reverse=False,
            )

            return result

    async def get_incident_details(self, work_item_id: int) -> dict:
        async with SessionLocal() as session:
            work_item = (
                await session.execute(select(WorkItem).where(WorkItem.id == work_item_id))
            ).scalar_one_or_none()
            if work_item is None:
                raise ValueError("Incident not found")
            rca = (
                await session.execute(select(RCARecord).where(RCARecord.work_item_id == work_item_id))
            ).scalar_one_or_none()

        signals_cursor = self.mongo_db.work_item_signals.find({"work_item_id": work_item_id}).sort(
            "received_at", -1
        )
        signals = []
        async for doc in signals_cursor:
            doc["_id"] = str(doc["_id"])
            signals.append(doc)

        return {
            "work_item": {
                "id": work_item.id,
                "component_id": work_item.component_id,
                "component_type": work_item.component_type,
                "severity": work_item.severity,
                "status": work_item.status,
                "created_at": work_item.created_at,
                "updated_at": work_item.updated_at,
            },
            "rca": None
            if rca is None
            else {
                "incident_start": rca.incident_start,
                "incident_end": rca.incident_end,
                "root_cause_category": rca.root_cause_category,
                "fix_applied": rca.fix_applied,
                "prevention_steps": rca.prevention_steps,
                "mttr_minutes": rca.mttr_minutes,
            },
            "signals": signals,
        }

    async def update_work_item_status(self, work_item_id: int, target_status: WorkItemStatus) -> dict:
        async with SessionLocal() as session:
            work_item = (
                await session.execute(select(WorkItem).where(WorkItem.id == work_item_id))
            ).scalar_one_or_none()
            if work_item is None:
                raise ValueError("Incident not found")

            rca = (
                await session.execute(select(RCARecord).where(RCARecord.work_item_id == work_item_id))
            ).scalar_one_or_none()
            has_complete_rca = bool(
                rca
                and rca.root_cause_category
                and rca.fix_applied
                and rca.prevention_steps
                and rca.incident_start
                and rca.incident_end
            )

            from app.workflow import WorkflowStateMachine

            new_status = WorkflowStateMachine.transition(
                current_status=WorkItemStatus(work_item.status),
                target_status=target_status,
                has_complete_rca=has_complete_rca,
            )
            work_item.status = new_status.value
            work_item.updated_at = datetime.now(tz=UTC)
            await session.commit()
            return {"work_item_id": work_item_id, "new_status": new_status.value}

    async def consume_throughput(self) -> int:
        count = self.ingested_since_last_log
        self.ingested_since_last_log = 0
        return count

    async def list_recent_aggregations(self, limit: int = 20) -> list[dict]:
        capped_limit = max(1, min(limit, 50))
        async with SessionLocal() as session:
            stmt = (
                select(IncidentAggregation)
                .order_by(IncidentAggregation.bucket_start.desc())
                .limit(capped_limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "bucket_start": row.bucket_start,
                    "component_type": row.component_type,
                    "severity": row.severity,
                    "count": row.count,
                }
                for row in rows
            ]

    @staticmethod
    def parse_datetime(value: str) -> datetime:
        return parser.isoparse(value)
