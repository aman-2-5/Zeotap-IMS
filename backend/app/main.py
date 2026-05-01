import asyncio
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis
from sqlalchemy import text

from app.db import Base, SessionLocal, engine
from app.schemas import RCAIn, SignalIn, StatusUpdateIn
from app.service import IncidentService
from app.settings import settings

signal_queue: asyncio.Queue[SignalIn] = asyncio.Queue(maxsize=settings.queue_max_size)
mongo_client: AsyncIOMotorClient | None = None
redis_client: Redis | None = None
service: IncidentService | None = None
worker_tasks: list[asyncio.Task] = []
throughput_task: asyncio.Task | None = None


class SlidingWindowRateLimiter:
    def __init__(self, limit_per_second: int) -> None:
        self.limit = limit_per_second
        self.bucket: dict[int, int] = {}
        self.lock = asyncio.Lock()

    async def allow(self) -> bool:
        now = int(time.time())
        async with self.lock:
            self.bucket = {k: v for k, v in self.bucket.items() if now - k <= 1}
            current = sum(self.bucket.values())
            if current >= self.limit:
                return False
            self.bucket[now] = self.bucket.get(now, 0) + 1
            return True


rate_limiter = SlidingWindowRateLimiter(settings.rate_limit_per_second)


async def queue_worker() -> None:
    assert service is not None
    while True:
        signal = await signal_queue.get()
        try:
            await service.record_signal(signal)
        except Exception as exc:
            print(f"Queue worker error: {exc}", flush=True)
            await asyncio.sleep(0.2)
            await signal_queue.put(signal)
        finally:
            signal_queue.task_done()


async def throughput_logger() -> None:
    assert service is not None
    while True:
        await asyncio.sleep(settings.throughput_log_interval_seconds)
        ingested = await service.consume_throughput()
        per_second = ingested / settings.throughput_log_interval_seconds
        print(f"[metrics] signals/sec={per_second:.2f} queue_size={signal_queue.qsize()}", flush=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global mongo_client, redis_client, service, worker_tasks, throughput_task
    mongo_client = AsyncIOMotorClient(settings.mongo_url)
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    service = IncidentService(mongo_client[settings.mongo_db], redis_client)

    # Mongo indexes for queryability and hot paths
    await mongo_client[settings.mongo_db].raw_signals.create_index("received_at")
    await mongo_client[settings.mongo_db].work_item_signals.create_index([("work_item_id", 1), ("received_at", -1)])

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    worker_tasks = [asyncio.create_task(queue_worker()) for _ in range(max(1, settings.worker_count))]
    throughput_task = asyncio.create_task(throughput_logger())
    yield
    for t in worker_tasks:
        t.cancel()
    if throughput_task:
        throughput_task.cancel()
    if redis_client:
        await redis_client.aclose()
    if mongo_client:
        mongo_client.close()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def ingress_rate_limit(request: Request, call_next):
    if request.url.path == "/ingest" and request.method == "POST":
        allowed = await rate_limiter.allow()
        if not allowed:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
    return await call_next(request)


@app.get("/health")
async def health():
    mongo_ok = False
    redis_ok = False
    pg_ok = False
    try:
        assert mongo_client is not None
        await mongo_client.admin.command("ping")
        mongo_ok = True
    except Exception:
        pass
    try:
        assert redis_client is not None
        await redis_client.ping()
        redis_ok = True
    except Exception:
        pass
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        pg_ok = True
    except Exception:
        pass
    return {"status": "ok" if all([mongo_ok, redis_ok, pg_ok]) else "degraded", "mongo": mongo_ok, "redis": redis_ok, "postgres": pg_ok}


@app.post("/ingest")
async def ingest_signal(signal: SignalIn):
    if signal_queue.full():
        raise HTTPException(status_code=503, detail="Backpressure active. Try again.")
    await signal_queue.put(signal)
    return {"accepted": True, "queued_at": datetime.now(tz=UTC), "queue_depth": signal_queue.qsize()}


@app.get("/incidents")
async def list_incidents(include_closed: bool = False, only_closed: bool = False):
    assert service is not None
    return await service.list_active_incidents(include_closed=include_closed, only_closed=only_closed)


@app.get("/incidents/{work_item_id}")
async def incident_details(work_item_id: int):
    assert service is not None
    try:
        return await service.get_incident_details(work_item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/incidents/{work_item_id}/status")
async def update_status(work_item_id: int, payload: StatusUpdateIn):
    assert service is not None
    try:
        return await service.update_work_item_status(work_item_id, payload.new_status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/incidents/{work_item_id}/rca")
async def upsert_rca(work_item_id: int, payload: RCAIn):
    assert service is not None
    try:
        return await service.create_or_update_rca(work_item_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/metrics/aggregations")
async def list_aggregations(limit: int = 20):
    assert service is not None
    return await service.list_recent_aggregations(limit=limit)
