from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from asgiref.sync import async_to_sync

from .models import Concert, TicketOrder
from . import services


class AsyncBuyTicketTests(TestCase):
    def setUp(self):
        self.concert = Concert.objects.create(
            title='Test Show',
            venue='Hall',
            starts_at=timezone.now(),
            ticket_price=Decimal('1000.00'),
            total_tickets=10,
            available_tickets=10,
            is_on_sale=True,
        )

    def test_buy_decrements_stock(self):
        order = async_to_sync(services.buy_ticket)(self.concert.id, 'a@example.com', 3)
        self.concert.refresh_from_db()
        self.assertEqual(order.quantity, 3)
        self.assertEqual(order.total_price, Decimal('3000.00'))
        self.assertEqual(self.concert.available_tickets, 7)

    def test_oversell_raises(self):
        with self.assertRaises(services.InsufficientTicketsError):
            async_to_sync(services.buy_ticket)(self.concert.id, 'b@example.com', 11)

    def test_async_dashboard_endpoint(self):
        response = async_to_sync(self.async_client.get)('/api/async/dashboard/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['mode'], 'async')
        self.assertGreaterEqual(payload['concerts'].__len__(), 1)

    def test_buy_endpoint(self):
        response = async_to_sync(self.async_client.post)(
            f'/api/async/concerts/{self.concert.id}/buy/',
            data='{"email":"c@example.com","quantity":1}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(TicketOrder.objects.count(), 1)
