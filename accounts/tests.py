from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class AuthenticationAPITests(APITestCase):
    def registration_data(self, username='new-user'):
        return {
            'username': username,
            'password': 'safe-password-123',
            'password_confirm': 'safe-password-123',
        }

    def create_user(self, username='existing-user'):
        return get_user_model().objects.create_user(
            username=username,
            password='safe-password-123',
        )

    def get_access_token(self):
        response = self.client.post(
            reverse('token_obtain_pair'),
            {'username': 'existing-user', 'password': 'safe-password-123'},
            format='json',
        )
        return response.data['access']

    def test_user_can_register(self):
        response = self.client.post(
            reverse('register'), self.registration_data(), format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(get_user_model().objects.filter(username='new-user').exists())
        self.assertNotIn('password', response.data)

    def test_duplicate_username_is_rejected(self):
        self.create_user()

        response = self.client.post(
            reverse('register'), self.registration_data('existing-user'), format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)

    def test_mismatched_passwords_are_rejected(self):
        data = self.registration_data()
        data['password_confirm'] = 'different-password-123'

        response = self.client.post(reverse('register'), data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password_confirm', response.data)

    def test_login_returns_access_and_refresh_tokens(self):
        self.create_user()

        response = self.client.post(
            reverse('token_obtain_pair'),
            {'username': 'existing-user', 'password': 'safe-password-123'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_refresh_returns_a_new_access_token(self):
        self.create_user()
        login_response = self.client.post(
            reverse('token_obtain_pair'),
            {'username': 'existing-user', 'password': 'safe-password-123'},
            format='json',
        )

        response = self.client.post(
            reverse('token_refresh'),
            {'refresh': login_response.data['refresh']},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_me_requires_authentication(self):
        response = self.client.get(reverse('me'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_view_me(self):
        self.create_user()
        access_token = self.get_access_token()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        response = self.client.get(reverse('me'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'existing-user')
