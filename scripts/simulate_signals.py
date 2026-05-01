import asyncio
import json
import random
from datetime import datetime, timezone

import httpx


async def send_signal(client: httpx.AsyncClient, signal: dict):
    body = {
        **signal,
        "occurred_at": datetime.now(tz=timezone.utc).isoformat(),
        "message": f"{signal['message']} (sample={random.randint(1000, 9999)})",
    }
    resp = await client.post("http://localhost:8000/ingest", json=body, timeout=10)
    if resp.status_code >= 300:
        print("failed", resp.status_code, resp.text)


async def main():
    with open("sample_signals.json", "r", encoding="utf-8") as f:
        signals = json.load(f)
    async with httpx.AsyncClient() as client:
        tasks = []
        for _ in range(300):
            signal = random.choice(signals)
            tasks.append(asyncio.create_task(send_signal(client, signal)))
        await asyncio.gather(*tasks)
    print("signal simulation complete")


if __name__ == "__main__":
    asyncio.run(main())
