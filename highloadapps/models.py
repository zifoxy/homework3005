from django.db import models
from django.utils import timezone


class Concert(models.Model):
    """Концерт — сущность, на которую приходится пиковая нагрузка при старте продаж."""

    title = models.CharField('название', max_length=200)
    venue = models.CharField('площадка', max_length=200)
    starts_at = models.DateTimeField('начало')
    ticket_price = models.DecimalField('цена билета', max_digits=10, decimal_places=2)
    total_tickets = models.PositiveIntegerField('всего билетов')
    available_tickets = models.PositiveIntegerField('доступно билетов')
    is_on_sale = models.BooleanField('продажа открыта', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'концерт'
        verbose_name_plural = 'концерты'
        ordering = ['starts_at']
        indexes = [
            models.Index(fields=['is_on_sale', 'starts_at']),
            models.Index(fields=['available_tickets']),
        ]

    def __str__(self):
        return self.title


class TicketOrder(models.Model):
    """Заказ билетов — создаётся массово при high-load."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает'
        CONFIRMED = 'confirmed', 'Подтверждён'
        CANCELLED = 'cancelled', 'Отменён'

    concert = models.ForeignKey(
        Concert,
        on_delete=models.CASCADE,
        related_name='orders',
        verbose_name='концерт',
    )
    buyer_email = models.EmailField('email покупателя')
    quantity = models.PositiveSmallIntegerField('количество', default=1)
    total_price = models.DecimalField('сумма', max_digits=12, decimal_places=2)
    status = models.CharField(
        'статус',
        max_length=20,
        choices=Status.choices,
        default=Status.CONFIRMED,
        db_index=True,
    )
    created_at = models.DateTimeField('создан', default=timezone.now, db_index=True)

    class Meta:
        verbose_name = 'заказ'
        verbose_name_plural = 'заказы'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['concert', 'status']),
            models.Index(fields=['buyer_email', 'created_at']),
        ]

    def __str__(self):
        return f'{self.buyer_email} × {self.quantity} ({self.concert_id})'


class RequestMetric(models.Model):
    """Метрики sync/async запросов для сравнения на демо-странице."""

    mode = models.CharField(max_length=20)  # sync | async
    endpoint = models.CharField(max_length=100)
    duration_ms = models.FloatField()
    queries_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'метрика'
        verbose_name_plural = 'метрики'
