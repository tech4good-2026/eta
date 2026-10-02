"""실제 캐시 메서드 + HTTP 테스트 대역의 요청 수. 외부 API/HTTP 서버 성능 시험이 아니다.

backend에서 PYTHONPATH=. uv run python tools/measure_source_cache.py
"""
import asyncio
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns

import httpx

from app.providers.seoul import SeoulDataClient


async def main(base_commit: str, provider_hash: str):
    calls = []
    async def fetch(_request):
        calls.append(perf_counter_ns())
        await asyncio.sleep(0.02)
        return httpx.Response(200, json={"getFcElvtr": {"row": [{"stnNm": "서울역"}]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(fetch)) as http:
        source = SeoulDataClient("fixture", "fixture", http)
        async def request():
            start = perf_counter_ns()
            await source.get_elevator("서울역")
            return perf_counter_ns() - start
        cold = await asyncio.gather(*(request() for _ in range(8)))
        cold_calls = len(calls)
        warm = await asyncio.gather(*(request() for _ in range(8)))
        assert cold_calls == 1 and len(calls) == 1
    print(json.dumps({
        "recorded_at": datetime.now(UTC).isoformat(),
        "base_commit": base_commit,
        "revision": "uncommitted local working tree; provider SHA256 identifies measured source",
        "provider_sha256": provider_hash,
        "conditions": {"callers_per_wave": 8, "repetitions": 1, "injected_delay_ms": 20,
                       "warmup": 0, "failures": 0, "transport": "httpx.MockTransport", "real_api_calls": 0},
        "cold": {"upstream_calls": cold_calls, "elapsed_ns_by_caller": cold},
        "warm": {"additional_upstream_calls": len(calls) - cold_calls, "elapsed_ns_by_caller": warm},
        "upstream_started_monotonic_ns": calls,
    }, indent=2))


if __name__ == "__main__":
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    source_hash = hashlib.sha256(Path("app/providers/seoul.py").read_bytes()).hexdigest()
    asyncio.run(main(revision, source_hash))
