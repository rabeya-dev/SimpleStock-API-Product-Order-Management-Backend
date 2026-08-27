from django.db import transaction
from rest_framework import serializers

from products.models import Product

from .models import Order, OrderItem


class OrderItemInputSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['product', 'quantity', 'unit_price', 'subtotal']
        read_only_fields = ['unit_price', 'subtotal']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemInputSerializer(many=True, allow_empty=False)

    class Meta:
        model = Order
        fields = [
            'id',
            'user',
            'status',
            'total',
            'created_at',
            'updated_at',
            'items',
        ]
        read_only_fields = [
            'id',
            'user',
            'status',
            'total',
            'created_at',
            'updated_at',
        ]

    def validate_items(self, items):
        product_ids = [item['product'].id for item in items]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError(
                'Each product can appear only once in an order.'
            )
        return items

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop('items')
        product_ids = [item['product'].id for item in items]
        products = Product.objects.select_for_update().in_bulk(product_ids)

        for item in items:
            product = products[item['product'].id]
            quantity = item['quantity']
            if quantity > product.stock:
                raise serializers.ValidationError(
                    f'Insufficient stock for product {product.id}. '
                    f'Available: {product.stock}, requested: {quantity}.'
                )

        order = Order.objects.create(**validated_data)
        total = 0

        for item in items:
            product = products[item['product'].id]
            quantity = item['quantity']
            subtotal = product.price * quantity
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                unit_price=product.price,
                subtotal=subtotal,
            )
            total += subtotal

        for item in items:
            product = products[item['product'].id]
            product.stock -= item['quantity']
            product.save(update_fields=['stock'])

        order.total = total
        order.save(update_fields=['total'])
        return order


class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)

    allowed_transitions = {
        Order.Status.PENDING: [Order.Status.CONFIRMED],
        Order.Status.CONFIRMED: [Order.Status.COMPLETED],
    }

    def validate_status(self, status):
        current_status = self.instance.status
        if status not in self.allowed_transitions.get(current_status, []):
            raise serializers.ValidationError(
                f'Cannot change order status from {current_status} to {status}.'
            )
        return status

    def update(self, instance, validated_data):
        instance.status = validated_data['status']
        instance.save(update_fields=['status', 'updated_at'])
        return instance
