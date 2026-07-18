import json
import time

from django.db.models import Count, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import services
from .models import Concert, TicketOrder


def _json_body(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    return json.loads(request.body.decode('utf-8'))


def _serialize_concert(c: Concert) -> dict:
    return {
        'id': c.id,
        'title': c.title,
        'venue': c.venue,
        'starts_at': c.starts_at.isoformat(),
        'ticket_price': str(c.ticket_price),
        'total_tickets': c.total_tickets,
        'available_tickets': c.available_tickets,
        'is_on_sale': c.is_on_sale,
    }


def _serialize_order(o: TicketOrder) -> dict:
    return {
        'id': o.id,
        'concert_id': o.concert_id,
        'concert_title': o.concert.title if hasattr(o, 'concert') and o.concert_id else None,
        'buyer_email': o.buyer_email,
        'quantity': o.quantity,
        'total_price': str(o.total_price),
        'status': o.status,
        'created_at': o.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

async def home(request: HttpRequest) -> HttpResponse:
    snapshot = await services.dashboard_snapshot()
    return render(request, 'highloadapps/home.html', {'snapshot': snapshot})


# ---------------------------------------------------------------------------
# Sync API — блокирует worker на время всех запросов к БД
# ---------------------------------------------------------------------------

@require_http_methods(['GET'])
def sync_dashboard(request: HttpRequest) -> JsonResponse:
    started = time.perf_counter()

    concerts = list(Concert.objects.filter(is_on_sale=True).order_by('starts_at')[:10])
    orders_count = TicketOrder.objects.count()
    confirmed_count = TicketOrder.objects.filter(status=TicketOrder.Status.CONFIRMED).count()

    duration_ms = (time.perf_counter() - started) * 1000
    return JsonResponse({
        'mode': 'sync',
        'duration_ms': round(duration_ms, 2),
        'orders_count': orders_count,
        'confirmed_count': confirmed_count,
        'concerts': [_serialize_concert(c) for c in concerts],
        'note': 'Последовательные sync-запросы: worker простаивает на каждом I/O.',
    })


@require_http_methods(['GET'])
def sync_concert_stats(request: HttpRequest, concert_id: int) -> JsonResponse:
    started = time.perf_counter()
    concert = get_object_or_404(Concert, pk=concert_id)
    aggregates = TicketOrder.objects.filter(
        concert_id=concert_id,
        status=TicketOrder.Status.CONFIRMED,
    ).aggregate(total_orders=Count('id'), tickets_sold=Sum('quantity'))
    recent = list(
        TicketOrder.objects.filter(concert_id=concert_id).order_by('-created_at')[:5]
    )
    duration_ms = (time.perf_counter() - started) * 1000

    return JsonResponse({
        'mode': 'sync',
        'duration_ms': round(duration_ms, 2),
        'concert': _serialize_concert(concert),
        'total_orders': aggregates['total_orders'] or 0,
        'tickets_sold': aggregates['tickets_sold'] or 0,
        'recent_orders': [_serialize_order(o) for o in recent],
    })


# ---------------------------------------------------------------------------
# Async API — event loop свободен на время ожидания БД
# ---------------------------------------------------------------------------

@require_http_methods(['GET'])
async def async_dashboard(request: HttpRequest) -> JsonResponse:
    started = time.perf_counter()
    snapshot = await services.dashboard_snapshot()
    duration_ms = (time.perf_counter() - started) * 1000
    await services.save_metric('async', 'dashboard', duration_ms, queries_count=3)

    return JsonResponse({
        'mode': 'async',
        'duration_ms': round(duration_ms, 2),
        'orders_count': snapshot['orders_count'],
        'confirmed_count': snapshot['confirmed_count'],
        'concerts': [_serialize_concert(c) for c in snapshot['concerts']],
        'note': 'asyncio.gather: независимые запросы к БД идут параллельно.',
    })


@require_http_methods(['GET'])
async def async_concerts(request: HttpRequest) -> JsonResponse:
    concerts = await services.list_concerts_on_sale()
    return JsonResponse({'count': len(concerts), 'results': [_serialize_concert(c) for c in concerts]})


@require_http_methods(['GET'])
async def async_concert_stats(request: HttpRequest, concert_id: int) -> JsonResponse:
    started = time.perf_counter()
    try:
        stats = await services.concert_stats(concert_id)
    except Concert.DoesNotExist:
        return JsonResponse({'error': 'Концерт не найден'}, status=404)

    duration_ms = (time.perf_counter() - started) * 1000
    await services.save_metric('async', f'concert_stats/{concert_id}', duration_ms, queries_count=3)

    return JsonResponse({
        'mode': 'async',
        'duration_ms': round(duration_ms, 2),
        'concert': _serialize_concert(stats['concert']),
        'total_orders': stats['total_orders'],
        'tickets_sold': stats['tickets_sold'],
        'available': stats['available'],
        'recent_orders': [_serialize_order(o) for o in stats['recent_orders']],
    })


@csrf_exempt
@require_http_methods(['POST'])
async def async_buy_ticket(request: HttpRequest, concert_id: int) -> JsonResponse:
    """
    Покупка билета под нагрузкой.
    Критическая секция (select_for_update) выполняется через sync_to_async.
    """
    try:
        payload = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    email = (payload.get('email') or '').strip().lower()
    quantity = int(payload.get('quantity') or 1)

    if not email or '@' not in email:
        return JsonResponse({'error': 'Укажите корректный email'}, status=400)
    if quantity < 1 or quantity > 10:
        return JsonResponse({'error': 'quantity должен быть от 1 до 10'}, status=400)

    started = time.perf_counter()
    try:
        order = await services.buy_ticket(concert_id, email, quantity)
    except Concert.DoesNotExist:
        return JsonResponse({'error': 'Концерт не найден'}, status=404)
    except services.SoldOutError as exc:
        return JsonResponse({'error': str(exc)}, status=409)
    except services.InsufficientTicketsError as exc:
        return JsonResponse({'error': str(exc)}, status=409)

    duration_ms = (time.perf_counter() - started) * 1000
    await services.save_metric('async', f'buy/{concert_id}', duration_ms, queries_count=2)

    return JsonResponse(
        {
            'ok': True,
            'duration_ms': round(duration_ms, 2),
            'order': _serialize_order(order),
        },
        status=201,
    )


@csrf_exempt
@require_http_methods(['POST'])
async def async_bulk_orders(request: HttpRequest, concert_id: int) -> JsonResponse:
    """Демо abulk_create — пакетная вставка заказов."""
    try:
        payload = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    count = min(int(payload.get('count') or 50), 500)
    started = time.perf_counter()
    try:
        created = await services.bulk_create_demo_orders(concert_id, count)
    except Concert.DoesNotExist:
        return JsonResponse({'error': 'Концерт не найден'}, status=404)

    duration_ms = (time.perf_counter() - started) * 1000
    return JsonResponse({
        'created': created,
        'duration_ms': round(duration_ms, 2),
        'mode': 'async bulk_create',
    })


@require_http_methods(['GET'])
async def async_orders_by_email(request: HttpRequest) -> JsonResponse:
    email = (request.GET.get('email') or '').strip().lower()
    if not email:
        return JsonResponse({'error': 'Параметр email обязателен'}, status=400)
    orders = await services.get_orders_for_email(email)
    return JsonResponse({
        'email': email,
        'count': len(orders),
        'results': [_serialize_order(o) for o in orders],
    })


@require_http_methods(['GET'])
async def compare_modes(request: HttpRequest) -> JsonResponse:
    """
    Сравнение sync vs async на одном наборе данных.
    Sync вызываем через sync_to_async, чтобы не блокировать loop в async-view.
    """
    from asgiref.sync import sync_to_async

    def _run_sync() -> dict:
        t0 = time.perf_counter()
        concerts = list(Concert.objects.filter(is_on_sale=True)[:10])
        orders = TicketOrder.objects.count()
        confirmed = TicketOrder.objects.filter(status=TicketOrder.Status.CONFIRMED).count()
        return {
            'duration_ms': round((time.perf_counter() - t0) * 1000, 2),
            'concerts': len(concerts),
            'orders': orders,
            'confirmed': confirmed,
        }

    sync_result = await sync_to_async(_run_sync, thread_sensitive=True)()

    t1 = time.perf_counter()
    snapshot = await services.dashboard_snapshot()
    async_ms = round((time.perf_counter() - t1) * 1000, 2)

    return JsonResponse({
        'sync': sync_result,
        'async': {
            'duration_ms': async_ms,
            'concerts': len(snapshot['concerts']),
            'orders': snapshot['orders_count'],
            'confirmed': snapshot['confirmed_count'],
        },
        'explanation': (
            'При одном запросе разница может быть небольшой. '
            'Выигрыш async проявляется при сотнях одновременных клиентов: '
            'event loop не блокируется на ожидании ответа БД.'
        ),
    })
