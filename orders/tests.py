from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from products.models import Product

from .models import Order, OrderItem
from .serializers import OrderSerializer


class OrderSerializerTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name='Notebook',
            price='25.50',
            stock=10,
        )

    def serializer_with_items(self, items):
        return OrderSerializer(data={'items': items})

    def test_valid_order_input_is_accepted(self):
        serializer = self.serializer_with_items(
            [{'product': self.product.id, 'quantity': 2}]
        )

        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['items'][0]['product'], self.product)

    def test_empty_items_are_rejected(self):
        serializer = self.serializer_with_items([])

        self.assertFalse(serializer.is_valid())
        self.assertIn('items', serializer.errors)

    def test_zero_and_negative_quantities_are_rejected(self):
        for quantity in [0, -1]:
            with self.subTest(quantity=quantity):
                serializer = self.serializer_with_items(
                    [{'product': self.product.id, 'quantity': quantity}]
                )

                self.assertFalse(serializer.is_valid())
                self.assertIn('quantity', serializer.errors['items'][0])

    def test_invalid_product_id_is_rejected(self):
        serializer = self.serializer_with_items(
            [{'product': 99999, 'quantity': 1}]
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('product', serializer.errors['items'][0])

    def test_duplicate_products_are_rejected(self):
        serializer = self.serializer_with_items(
            [
                {'product': self.product.id, 'quantity': 1},
                {'product': self.product.id, 'quantity': 2},
            ]
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('items', serializer.errors)

    def test_backend_controlled_fields_are_not_writable(self):
        data = {
            'user': 99999,
            'status': Order.Status.COMPLETED,
            'total': '999.99',
            'items': [
                {
                    'id': 99999,
                    'order': 99999,
                    'product': self.product.id,
                    'quantity': 1,
                    'unit_price': '999.99',
                    'subtotal': '999.99',
                }
            ],
        }
        serializer = OrderSerializer(data=data)

        self.assertTrue(serializer.is_valid())
        self.assertEqual(list(serializer.validated_data), ['items'])
        self.assertEqual(
            list(serializer.validated_data['items'][0]), ['product', 'quantity']
        )


class OrderAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='order-user',
            password='test-password-123',
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.user)}'
        )
        self.product = Product.objects.create(
            name='Notebook',
            price='25.50',
            stock=10,
        )

    def order_payload(self, items):
        return {'items': items}

    def test_authenticated_user_can_create_order(self):
        response = self.client.post(
            reverse('order-create'),
            self.order_payload([{'product': self.product.id, 'quantity': 2}]),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get()
        item = OrderItem.objects.get()
        self.assertEqual(order.user, self.user)
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, Decimal('25.50'))
        self.assertEqual(item.subtotal, Decimal('51.00'))
        self.assertEqual(order.total, Decimal('51.00'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(response.data['items'][0]['unit_price'], '25.50')
        self.assertEqual(response.data['items'][0]['subtotal'], '51.00')

    def test_exact_stock_quantity_is_allowed(self):
        self.product.stock = 5
        self.product.save(update_fields=['stock'])

        response = self.client.post(
            reverse('order-create'),
            self.order_payload([{'product': self.product.id, 'quantity': 5}]),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

    def test_insufficient_stock_rejects_order_without_changes(self):
        self.product.stock = 3
        self.product.save(update_fields=['stock'])

        response = self.client.post(
            reverse('order-create'),
            self.order_payload([{'product': self.product.id, 'quantity': 5}]),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Insufficient stock', str(response.data))
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)


class OrderStatusAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='status-user',
            password='test-password-123',
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.user)}'
        )
        self.product = Product.objects.create(
            name='Notebook',
            price='25.50',
            stock=10,
        )
        self.order = Order.objects.create(
            user=self.user,
            total=Decimal('25.50'),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            unit_price=Decimal('25.50'),
            subtotal=Decimal('25.50'),
        )

    def status_url(self):
        return reverse('order-status', args=[self.order.id])

    def update_status(self, new_status):
        return self.client.patch(
            self.status_url(),
            {'status': new_status},
            format='json',
        )

    def test_pending_order_can_be_confirmed(self):
        response = self.update_status(Order.Status.CONFIRMED)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
        self.assertEqual(response.data['status'], Order.Status.CONFIRMED)

    def test_confirmed_order_can_be_completed(self):
        self.order.status = Order.Status.CONFIRMED
        self.order.save(update_fields=['status'])

        response = self.update_status(Order.Status.COMPLETED)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.COMPLETED)

    def test_invalid_status_is_rejected(self):
        response = self.update_status('does-not-exist')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_pending_order_cannot_skip_to_completed(self):
        response = self.update_status(Order.Status.COMPLETED)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_completed_order_cannot_move_backward(self):
        self.order.status = Order.Status.COMPLETED
        self.order.save(update_fields=['status'])

        response = self.update_status(Order.Status.PENDING)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.COMPLETED)

    def test_user_cannot_modify_another_users_order(self):
        other_user = get_user_model().objects.create_user(
            username='other-status-user',
            password='test-password-123',
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(other_user)}'
        )

        response = self.update_status(Order.Status.CONFIRMED)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_unauthenticated_user_cannot_update_status(self):
        self.client.credentials()

        response = self.update_status(Order.Status.CONFIRMED)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_status_update_does_not_change_order_data_or_stock(self):
        original_total = self.order.total
        original_unit_price = self.order.items.get().unit_price
        original_subtotal = self.order.items.get().subtotal
        original_stock = self.product.stock

        response = self.update_status(Order.Status.CONFIRMED)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        item = self.order.items.get()
        self.assertEqual(self.order.total, original_total)
        self.assertEqual(item.unit_price, original_unit_price)
        self.assertEqual(item.subtotal, original_subtotal)
        self.assertEqual(self.product.stock, original_stock)


class OrderCreationRemainderAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='order-remainder-user',
            password='test-password-123',
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.user)}'
        )
        self.product = Product.objects.create(
            name='Notebook',
            price='25.50',
            stock=10,
        )

    def order_payload(self, items):
        return {'items': items}

    def test_multiple_products_are_calculated(self):
        second_product = Product.objects.create(name='Pen', price='10.00', stock=5)

        response = self.client.post(
            reverse('order-create'),
            self.order_payload(
                [
                    {'product': self.product.id, 'quantity': 2},
                    {'product': second_product.id, 'quantity': 3},
                ]
            ),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get()
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(order.total, Decimal('81.00'))
        self.product.refresh_from_db()
        second_product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(second_product.stock, 2)
        self.assertEqual(
            set(order.items.values_list('unit_price', 'subtotal')),
            {
                (Decimal('25.50'), Decimal('51.00')),
                (Decimal('10.00'), Decimal('30.00')),
            },
        )

    def test_client_cannot_control_total_or_unit_price(self):
        response = self.client.post(
            reverse('order-create'),
            {
                'total': '1.00',
                'items': [
                    {
                        'product': self.product.id,
                        'quantity': 2,
                        'unit_price': '1.00',
                    }
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get()
        item = order.items.get()
        self.assertEqual(order.total, Decimal('51.00'))
        self.assertEqual(item.unit_price, Decimal('25.50'))

    def test_insufficient_stock_in_one_item_does_not_deduct_another(self):
        second_product = Product.objects.create(name='Pen', price='10.00', stock=2)

        response = self.client.post(
            reverse('order-create'),
            self.order_payload(
                [
                    {'product': self.product.id, 'quantity': 3},
                    {'product': second_product.id, 'quantity': 5},
                ]
            ),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.product.refresh_from_db()
        second_product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(second_product.stock, 2)


class OrderCancellationAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='cancel-user',
            password='test-password-123',
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.user)}'
        )
        self.product = Product.objects.create(
            name='Notebook',
            price='25.50',
            stock=8,
        )
        self.order = Order.objects.create(
            user=self.user,
            total=Decimal('51.00'),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('25.50'),
            subtotal=Decimal('51.00'),
        )

    def cancel_order(self):
        return self.client.post(
            reverse('order-cancel', args=[self.order.id]),
            format='json',
        )

    def test_pending_order_can_be_cancelled_and_stock_restored(self):
        response = self.cancel_order()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.stock, 10)

    def test_confirmed_order_can_be_cancelled(self):
        self.order.status = Order.Status.CONFIRMED
        self.order.save(update_fields=['status'])

        response = self.cancel_order()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_completed_order_cannot_be_cancelled(self):
        self.order.status = Order.Status.COMPLETED
        self.order.save(update_fields=['status'])

        response = self.cancel_order()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.COMPLETED)
        self.assertEqual(self.product.stock, 8)

    def test_cancelled_order_cannot_be_cancelled_again(self):
        self.order.status = Order.Status.CANCELLED
        self.order.save(update_fields=['status'])

        response = self.cancel_order()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.stock, 8)

    def test_multiple_product_stock_is_restored(self):
        second_product = Product.objects.create(name='Pen', price='10.00', stock=2)
        OrderItem.objects.create(
            order=self.order,
            product=second_product,
            quantity=3,
            unit_price=Decimal('10.00'),
            subtotal=Decimal('30.00'),
        )

        response = self.cancel_order()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        second_product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(second_product.stock, 5)

    def test_cancellation_does_not_change_financial_data_or_quantity(self):
        item = self.order.items.get()
        original_values = (
            self.order.total,
            item.unit_price,
            item.subtotal,
            item.quantity,
        )

        response = self.cancel_order()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(
            (self.order.total, item.unit_price, item.subtotal, item.quantity),
            original_values,
        )

    def test_user_cannot_cancel_another_users_order(self):
        other_user = get_user_model().objects.create_user(
            username='other-cancel-user',
            password='test-password-123',
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(other_user)}'
        )

        response = self.cancel_order()

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertEqual(self.product.stock, 8)

    def test_unauthenticated_user_cannot_cancel_order(self):
        self.client.credentials()

        response = self.cancel_order()

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertEqual(self.product.stock, 8)

    def test_cancellation_failure_rolls_back_stock_and_status(self):
        second_product = Product.objects.create(name='Pen', price='10.00', stock=5)
        OrderItem.objects.create(
            order=self.order,
            product=second_product,
            quantity=2,
            unit_price=Decimal('10.00'),
            subtotal=Decimal('20.00'),
        )
        original_save = Product.save
        save_calls = 0

        def fail_on_second_stock_save(product, *args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 2:
                raise RuntimeError('simulated restoration failure')
            return original_save(product, *args, **kwargs)

        with patch.object(Product, 'save', autospec=True, side_effect=fail_on_second_stock_save):
            with self.assertRaises(RuntimeError):
                self.cancel_order()

        self.order.refresh_from_db()
        self.product.refresh_from_db()
        second_product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(second_product.stock, 5)


class OrderCreationFinalRemainderAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='order-final-user',
            password='test-password-123',
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.user)}'
        )
        self.product = Product.objects.create(
            name='Notebook',
            price='25.50',
            stock=10,
        )

    def order_payload(self, items):
        return {'items': items}

    def test_zero_stock_rejects_order(self):
        self.product.stock = 0
        self.product.save(update_fields=['stock'])

        response = self.client.post(
            reverse('order-create'),
            self.order_payload([{'product': self.product.id, 'quantity': 1}]),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

    def test_workflow_failure_rolls_back_order_items_and_stock(self):
        second_product = Product.objects.create(name='Pen', price='10.00', stock=5)
        original_save = Product.save
        save_calls = 0

        def fail_on_second_stock_save(product, *args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 2:
                raise RuntimeError('simulated stock update failure')
            return original_save(product, *args, **kwargs)

        with patch.object(Product, 'save', autospec=True, side_effect=fail_on_second_stock_save):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse('order-create'),
                    self.order_payload(
                        [
                            {'product': self.product.id, 'quantity': 3},
                            {'product': second_product.id, 'quantity': 2},
                        ]
                    ),
                    format='json',
                )

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.product.refresh_from_db()
        second_product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(second_product.stock, 5)

    def test_unauthenticated_user_cannot_create_order(self):
        self.client.credentials()

        response = self.client.post(
            reverse('order-create'),
            self.order_payload([{'product': self.product.id, 'quantity': 1}]),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Order.objects.count(), 0)

    def test_existing_serializer_validation_is_used_by_api(self):
        invalid_items = [
            [],
            [{'product': self.product.id, 'quantity': 0}],
            [{'product': self.product.id, 'quantity': -1}],
            [{'product': 99999, 'quantity': 1}],
            [
                {'product': self.product.id, 'quantity': 1},
                {'product': self.product.id, 'quantity': 2},
            ],
        ]

        for items in invalid_items:
            with self.subTest(items=items):
                response = self.client.post(
                    reverse('order-create'),
                    self.order_payload(items),
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertEqual(Order.objects.count(), 0)


class OrderWorkflowAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='workflow-user',
            password='test-password-123',
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.user)}'
        )
        self.product = Product.objects.create(
            name='Notebook',
            price='25.50',
            stock=10,
        )

    def create_order(self, quantity):
        response = self.client.post(
            reverse('order-create'),
            {'items': [{'product': self.product.id, 'quantity': quantity}]},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return Order.objects.get()

    def test_order_can_follow_pending_confirmed_completed_lifecycle(self):
        order = self.create_order(2)

        confirmed_response = self.client.patch(
            reverse('order-status', args=[order.id]),
            {'status': Order.Status.CONFIRMED},
            format='json',
        )
        completed_response = self.client.patch(
            reverse('order-status', args=[order.id]),
            {'status': Order.Status.COMPLETED},
            format='json',
        )

        self.assertEqual(confirmed_response.status_code, status.HTTP_200_OK)
        self.assertEqual(completed_response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(self.product.stock, 8)

    def test_order_can_be_cancelled_and_restore_deducted_stock(self):
        order = self.create_order(3)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)

        response = self.client.post(
            reverse('order-cancel', args=[order.id]),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.stock, 10)
