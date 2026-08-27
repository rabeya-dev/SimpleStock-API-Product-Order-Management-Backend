from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from .models import Product


class ProductAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='product-user',
            password='test-password-123',
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.user)}'
        )
        self.product = Product.objects.create(
            name='Notebook',
            description='A simple notebook',
            price='25.50',
            stock=10,
        )

    def test_unauthenticated_user_cannot_list_products(self):
        self.client.credentials()

        response = self.client.get(reverse('product-list'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_create_product(self):
        response = self.client.post(
            reverse('product-list'),
            {
                'name': 'Pen',
                'description': 'Blue ink pen',
                'price': '10.00',
                'stock': 25,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(response.data['price'], '10.00')

    def test_authenticated_user_can_list_products(self):
        response = self.client.get(reverse('product-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_authenticated_user_can_retrieve_product(self):
        response = self.client.get(reverse('product-detail', args=[self.product.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.product.name)

    def test_authenticated_user_can_update_product(self):
        response = self.client.patch(
            reverse('product-detail', args=[self.product.id]),
            {'stock': 5},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)

    def test_authenticated_user_can_delete_product(self):
        response = self.client.delete(reverse('product-detail', args=[self.product.id]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Product.objects.filter(id=self.product.id).exists())

    def test_invalid_product_data_is_rejected(self):
        response = self.client.post(
            reverse('product-list'),
            {'name': 'Pen', 'price': '-10.00', 'stock': -1},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('price', response.data)
        self.assertIn('stock', response.data)

    def test_missing_product_returns_not_found(self):
        response = self.client.get(reverse('product-detail', args=[99999]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_search_returns_matching_products_case_insensitively(self):
        Product.objects.create(name='iPhone', price='1000.00', stock=5)
        Product.objects.create(name='Samsung Phone', price='900.00', stock=5)
        Product.objects.create(name='Laptop', price='1200.00', stock=3)

        lowercase_response = self.client.get(
            reverse('product-list'), {'search': 'phone'}
        )
        uppercase_response = self.client.get(
            reverse('product-list'), {'search': 'Phone'}
        )

        self.assertEqual(lowercase_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [product['name'] for product in lowercase_response.data],
            ['iPhone', 'Samsung Phone'],
        )
        self.assertEqual(uppercase_response.data, lowercase_response.data)

    def test_search_with_no_matches_returns_an_empty_list(self):
        response = self.client.get(reverse('product-list'), {'search': 'xyz123'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_list_without_search_returns_all_products(self):
        Product.objects.create(name='Laptop', price='1200.00', stock=3)

        response = self.client.get(reverse('product-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_unauthenticated_user_cannot_search_products(self):
        self.client.credentials()

        response = self.client.get(reverse('product-list'), {'search': 'phone'})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
