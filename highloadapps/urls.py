from django.urls import path

from . import views

app_name = 'highloadapps'

urlpatterns = [
    path('', views.home, name='home'),

    # Sync (для сравнения)
    path('api/sync/dashboard/', views.sync_dashboard, name='sync_dashboard'),
    path('api/sync/concerts/<int:concert_id>/stats/', views.sync_concert_stats, name='sync_concert_stats'),

    # Async high-load API
    path('api/async/dashboard/', views.async_dashboard, name='async_dashboard'),
    path('api/async/concerts/', views.async_concerts, name='async_concerts'),
    path('api/async/concerts/<int:concert_id>/stats/', views.async_concert_stats, name='async_concert_stats'),
    path('api/async/concerts/<int:concert_id>/buy/', views.async_buy_ticket, name='async_buy_ticket'),
    path('api/async/concerts/<int:concert_id>/bulk/', views.async_bulk_orders, name='async_bulk_orders'),
    path('api/async/orders/', views.async_orders_by_email, name='async_orders_by_email'),
    path('api/compare/', views.compare_modes, name='compare_modes'),
]
