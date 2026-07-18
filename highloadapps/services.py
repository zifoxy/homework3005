"""
Асинхронный слой доступа к БД.

В high-load системах узкое место — ожидание I/O (диск/сеть БД).
Async ORM не ускоряет один SQL-запрос, но позволяет event loop
обрабатывать другие запросы, пока текущий ждёт ответ от БД.
Параллельные независимые запросы объединяем через asyncio.gather.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from .models import Concert, RequestMetric, TicketOrder


class SoldOutError(Exception):
    """Билеты закончились или продажи закрыты."""


class InsufficientTicketsError(Exception):
    """Недостаточно свободных билетов."""


# ---------------------------------------------------------------------------
# Async CRUD / чтение
# ---------------------------------------------------------------------------

async def list_concerts_on_sale(*, limit: int = 50) -> list[Concert]:
    return [
        concert
        async for concert in Concert.objects.filter(is_on_sale=True).order_by('starts_at')[:limit]
    ]


async def get_concert(concert_id: int) -> Concert:
    return await Concert.objects.aget(pk=concert_id)


async def get_orders_for_email(email: str, *, limit: int = 20) -> list[TicketOrder]:
    return [
        order
        async for order in (
            TicketOrder.objects.select_related('concert')
            .filter(buyer_email=email)
            .order_by('-created_at')[:limit]
        )
    ]


async def concert_stats(concert_id: int) -> dict:
    """Независимые запросы выполняем параллельно — ключ к high-load."""
    concert, aggregates = await asyncio.gather(
        Concert.objects.aget(pk=concert_id),
        TicketOrder.objects.filter(
            concert_id=concert_id,
            status=TicketOrder.Status.CONFIRMED,
        ).aaggregate(total_orders=Count('id'), tickets_sold=Sum('quantity')),
    )
    recent = [
        order
        async for order in (
            TicketOrder.objects.filter(concert_id=concert_id).order_by('-created_at')[:5]
        )
    ]

    return {
        'concert': concert,
        'total_orders': aggregates['total_orders'] or 0,
        'tickets_sold': aggregates['tickets_sold'] or 0,
        'available': concert.available_tickets,
        'recent_orders': recent,
    }


async def dashboard_snapshot() -> dict:
    """
    Параллельный snapshot для дашборда:
    несколько независимых чтений БД без блокировки друг друга.
    """
    concerts, orders_count, confirmed_count = await asyncio.gather(
        list_concerts_on_sale(limit=10),
        TicketOrder.objects.acount(),
        TicketOrder.objects.filter(status=TicketOrder.Status.CONFIRMED).acount(),
    )
    metrics = [
        m async for m in RequestMetric.objects.order_by('-created_at')[:10]
    ]

    return {
        'concerts': concerts,
        'orders_count': orders_count,
        'confirmed_count': confirmed_count,
        'metrics': metrics,
        'generated_at': timezone.now(),
    }


# ---------------------------------------------------------------------------
# Покупка билета: критическая секция с select_for_update
# ---------------------------------------------------------------------------

def _buy_ticket_sync(concert_id: int, buyer_email: str, quantity: int) -> TicketOrder:
    """
    Синхронная транзакция с блокировкой строки.
    select_for_update предотвращает overselling при конкурентных покупках.
    """
    with transaction.atomic():
        concert = Concert.objects.select_for_update().get(pk=concert_id)

        if not concert.is_on_sale:
            raise SoldOutError('Продажа закрыта')
        if concert.available_tickets < quantity:
            raise InsufficientTicketsError(
                f'Доступно только {concert.available_tickets} билет(ов)'
            )

        concert.available_tickets -= quantity
        concert.save(update_fields=['available_tickets'])

        return TicketOrder.objects.create(
            concert=concert,
            buyer_email=buyer_email,
            quantity=quantity,
            total_price=Decimal(concert.ticket_price) * quantity,
            status=TicketOrder.Status.CONFIRMED,
        )


async def buy_ticket(concert_id: int, buyer_email: str, quantity: int = 1) -> TicketOrder:
    """
    Async-обёртка над транзакцией покупки.

    Django ORM пока выполняет select_for_update / atomic в sync-контексте,
    поэтому критическую секцию выносим в sync_to_async(thread_sensitive=True),
    чтобы не блокировать event loop целиком на время ожидания lock'а.
    """
    return await sync_to_async(_buy_ticket_sync, thread_sensitive=True)(
        concert_id, buyer_email, quantity
    )


async def bulk_create_demo_orders(concert_id: int, count: int = 50) -> int:
    """abulk_create — эффективная пакетная вставка под нагрузкой."""
    concert = await Concert.objects.aget(pk=concert_id)
    price = Decimal(concert.ticket_price)
    orders = [
        TicketOrder(
            concert_id=concert_id,
            buyer_email=f'loadtest{i}@example.com',
            quantity=1,
            total_price=price,
            status=TicketOrder.Status.CONFIRMED,
        )
        for i in range(count)
    ]
    created = await TicketOrder.objects.abulk_create(orders, batch_size=100)
    return len(created)


async def save_metric(mode: str, endpoint: str, duration_ms: float, queries_count: int = 0) -> None:
    await RequestMetric.objects.acreate(
        mode=mode,
        endpoint=endpoint,
        duration_ms=duration_ms,
        queries_count=queries_count,
    )
