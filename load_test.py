"""
Простой нагрузочный клиент: много одновременных async HTTP-запросов.

Показывает, как ASGI + async views держат конкуренцию лучше,
чем последовательная обработка sync-воркером.

Запуск (сервер уже поднят на :8000):
    python load_test.py
    python load_test.py --url http://127.0.0.1:8000 --concurrency 100 --requests 200
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

try:
    import httpx
except ImportError as exc:
    raise SystemExit('Установите httpx: pip install httpx') from exc


async def hit(client: httpx.AsyncClient, url: str, sem: asyncio.Semaphore) -> float:
    async with sem:
        t0 = time.perf_counter()
        response = await client.get(url)
        response.raise_for_status()
        return (time.perf_counter() - t0) * 1000


async def run_batch(base: str, path: str, total: int, concurrency: int) -> dict:
    url = base.rstrip('/') + path
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)

    async with httpx.AsyncClient(timeout=30.0, limits=limits) as client:
        started = time.perf_counter()
        timings = await asyncio.gather(*[hit(client, url, sem) for _ in range(total)])
        wall = (time.perf_counter() - started) * 1000

    return {
        'path': path,
        'requests': total,
        'concurrency': concurrency,
        'wall_ms': round(wall, 1),
        'rps': round(total / (wall / 1000), 1),
        'avg_ms': round(statistics.mean(timings), 2),
        'p95_ms': round(statistics.quantiles(timings, n=20)[18], 2) if total >= 20 else round(max(timings), 2),
        'max_ms': round(max(timings), 2),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description='Load test FlashSale async API')
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--concurrency', type=int, default=50)
    parser.add_argument('--requests', type=int, default=100)
    args = parser.parse_args()

    print(f'Target: {args.url}')
    print(f'Requests: {args.requests}, concurrency: {args.concurrency}\n')

    for path in ('/api/async/dashboard/', '/api/sync/dashboard/', '/api/compare/'):
        try:
            result = await run_batch(args.url, path, args.requests, args.concurrency)
        except Exception as exc:
            print(f'{path}: ERROR — {exc}')
            continue
        print(
            f"{result['path']}\n"
            f"  wall={result['wall_ms']} ms  rps={result['rps']}  "
            f"avg={result['avg_ms']} ms  p95={result['p95_ms']} ms  max={result['max_ms']} ms\n"
        )


if __name__ == '__main__':
    asyncio.run(main())
