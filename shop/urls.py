from django.urls import path
from . import views

urlpatterns = [
    path('create_checkout_session', views.create_checkout_session),
    path('stripe_webhook', views.stripe_webhook),
    path('order_status', views.get_order_status),
]
