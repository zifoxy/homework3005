from django.contrib import admin

from .models import Concert, RequestMetric, TicketOrder


@admin.register(Concert)
class ConcertAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'venue',
        'starts_at',
        'ticket_price',
        'available_tickets',
        'total_tickets',
        'is_on_sale',
    )
    list_filter = ('is_on_sale',)
    search_fields = ('title', 'venue')


@admin.register(TicketOrder)
class TicketOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'concert', 'buyer_email', 'quantity', 'total_price', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('buyer_email',)
    raw_id_fields = ('concert',)


@admin.register(RequestMetric)
class RequestMetricAdmin(admin.ModelAdmin):
    list_display = ('mode', 'endpoint', 'duration_ms', 'queries_count', 'created_at')
    list_filter = ('mode',)
