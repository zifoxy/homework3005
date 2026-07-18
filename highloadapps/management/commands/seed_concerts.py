from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from highloadapps.models import Concert


class Command(BaseCommand):
    help = 'Создаёт демо-концерты для flash-sale сценария'

    def handle(self, *args, **options):
        now = timezone.now()
        fixtures = [
            {
                'title': 'Aurora Live - Night Drive',
                'venue': 'Stadium Arena',
                'starts_at': now + timedelta(days=14),
                'ticket_price': Decimal('3500.00'),
                'total_tickets': 5000,
                'available_tickets': 5000,
            },
            {
                'title': 'Neon Pulse Festival',
                'venue': 'Open Air Park',
                'starts_at': now + timedelta(days=30),
                'ticket_price': Decimal('2200.00'),
                'total_tickets': 12000,
                'available_tickets': 12000,
            },
            {
                'title': 'Jazz After Dark',
                'venue': 'Blue Note Hall',
                'starts_at': now + timedelta(days=7),
                'ticket_price': Decimal('1800.00'),
                'total_tickets': 800,
                'available_tickets': 800,
            },
            {
                'title': 'Sold Out Demo (закрыт)',
                'venue': 'Small Club',
                'starts_at': now + timedelta(days=3),
                'ticket_price': Decimal('999.00'),
                'total_tickets': 100,
                'available_tickets': 0,
                'is_on_sale': False,
            },
        ]

        created = 0
        for data in fixtures:
            obj, was_created = Concert.objects.update_or_create(
                title=data['title'],
                defaults=data,
            )
            created += int(was_created)
            self.stdout.write(f'  • {obj.title} (id={obj.id}, available={obj.available_tickets})')

        self.stdout.write(self.style.SUCCESS(f'Готово: новых записей {created}, всего концертов {Concert.objects.count()}'))
