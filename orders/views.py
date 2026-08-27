from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.generics import CreateAPIView
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from products.models import Product

from .models import Order
from .serializers import OrderSerializer, OrderStatusUpdateSerializer


class OrderCreateView(CreateAPIView):
	serializer_class = OrderSerializer
	permission_classes = [IsAuthenticated]

	def perform_create(self, serializer):
		serializer.save(user=self.request.user)


class OrderStatusUpdateView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(
		request=OrderStatusUpdateSerializer,
		responses=OrderSerializer,
		description='Advance an order through the pending, confirmed, and completed lifecycle.',
	)
	def patch(self, request, pk):
		order = get_object_or_404(Order, pk=pk, user=request.user)
		serializer = OrderStatusUpdateSerializer(order, data=request.data)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(OrderSerializer(order).data)


class OrderCancellationView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(
		request=None,
		responses=OrderSerializer,
		description='Cancel a pending or confirmed order and restore its item quantities to stock.',
	)
	@transaction.atomic
	def post(self, request, pk):
		order = get_object_or_404(
			Order.objects.select_for_update(),
			pk=pk,
			user=request.user,
		)
		if order.status not in [Order.Status.PENDING, Order.Status.CONFIRMED]:
			raise ValidationError(
				f'Order cannot be cancelled from status {order.status}.'
			)

		items = list(order.items.all())
		products = Product.objects.select_for_update().in_bulk(
			[item.product_id for item in items]
		)
		for item in items:
			product = products[item.product_id]
			product.stock += item.quantity
			product.save(update_fields=['stock'])

		order.status = Order.Status.CANCELLED
		order.save(update_fields=['status', 'updated_at'])
		return Response(OrderSerializer(order).data)
