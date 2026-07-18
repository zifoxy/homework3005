# FlashSale — асинхронные взаимодействия с БД в high-load системах

Учебный проект: сервис flash-sale продажи билетов на концерты.
Демонстрирует Django Async ORM, ASGI и параллельные запросы к БД.

## Идея

При старте продаж тысячи пользователей одновременно бронируют билеты.
Синхронный worker на каждый SQL-запрос **блокируется** и ждёт ответ БД.
Async-подход не ускоряет один SQL, но позволяет event loop обслуживать
другие запросы, пока текущий ждёт I/O. Независимые чтения объединяются
через `asyncio.gather`.

## Стек

- Django 6 (async views + async ORM: `aget`, `afilter`, `acreate`, `abulk_create`)
- ASGI-сервер: Uvicorn
- SQLite (для локальной учёбы; в проде — PostgreSQL + пул соединений)

## Быстрый старт

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_concerts

# Важно: ASGI, не runserver-WSGI
uvicorn config.asgi:application --reload
```

Откройте http://127.0.0.1:8000/

## API

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/async/dashboard/` | Параллельный snapshot (`asyncio.gather`) |
| GET | `/api/sync/dashboard/` | Тот же snapshot синхронно (для сравнения) |
| GET | `/api/async/concerts/` | Список концертов (async ORM) |
| GET | `/api/async/concerts/<id>/stats/` | Статистика концерта |
| POST | `/api/async/concerts/<id>/buy/` | Покупка билета (`select_for_update`) |
| POST | `/api/async/concerts/<id>/bulk/` | Пакетная вставка (`abulk_create`) |
| GET | `/api/async/orders/?email=` | Заказы покупателя |
| GET | `/api/compare/` | Сравнение sync vs async на одном наборе |

### Пример покупки

```bash
curl -X POST http://127.0.0.1:8000/api/async/concerts/1/buy/ ^
  -H "Content-Type: application/json" ^
  -d "{\"email\":\"fan@example.com\",\"quantity\":2}"
```

## Нагрузочный тест

```bash
python load_test.py --concurrency 50 --requests 100
```

Скрипт бьёт sync и async endpoints конкурентными запросами и печатает RPS / latency.

## Что смотреть в коде

1. `highloadapps/services.py` — async слой БД, `asyncio.gather`, покупка с блокировкой строки
2. `highloadapps/views.py` — async / sync views рядом для сравнения
3. `load_test.py` — имитация high-load клиента на `httpx` + `asyncio`

## High-load практики (кратко)

| Практика | Как в проекте |
|----------|----------------|
| Не блокировать event loop | `async def` views + `await` ORM |
| Параллелить независимые запросы | `asyncio.gather` в `dashboard_snapshot` |
| Защита от overselling | `select_for_update` в транзакции покупки |
| Пакетные вставки | `abulk_create` |
| ASGI под конкуренцию | Uvicorn (`config.asgi`) |
| Индексы под частые фильтры | `Meta.indexes` в моделях |

В продакшене дополнительно: PostgreSQL, connection pool (PgBouncer),
кэш (Redis), очереди для тяжёлых операций, горизонтальное масштабирование ASGI-воркеров.
