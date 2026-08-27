from django.urls import path

from .views import (
    OrderCancellationView,
    OrderCreateView,
    OrderStatusUpdateView,
)


urlpatterns = [
    path('', OrderCreateView.as_view(), name='order-create'),
    path('<int:pk>/status/', OrderStatusUpdateView.as_view(), name='order-status'),
    path('<int:pk>/cancel/', OrderCancellationView.as_view(), name='order-cancel'),
]
