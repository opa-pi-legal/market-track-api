from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from api.management.commands.consume_events import handle_event
from api.models import Product


class ProductApiTests(TestCase):
    def setUp(self):
        self.user_client = APIClient()
        self.user_client.force_authenticate(
            user=SimpleNamespace(id=1, is_authenticated=True, is_staff=False),
            token={'is_staff': False},
        )
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(
            user=SimpleNamespace(id=99, is_authenticated=True, is_staff=True),
            token={'is_staff': True},
        )

        self.p1 = Product.objects.create(
            group_id='1',
            name='Produto Privado G1',
            added_by='1',
            is_global=False,
        )
        self.p2 = Product.objects.create(
            group_id='2',
            name='Produto Privado G2',
            added_by='2',
            is_global=False,
        )

    def test_health_and_swagger_docs_public(self):
        anon = APIClient()
        self.assertEqual(anon.get('/product-api/health/').status_code, 200)
        self.assertEqual(anon.get('/product-api/docs/').status_code, 200)

    @patch('api.views.publish_event')
    def test_manual_product_creation_is_always_private(self, mock_pub):
        res = self.user_client.post(
            '/product-api/api/products/',
            {
                'group_id': '1',
                'name': 'Tentativa Global Manual',
                'is_global': True,
                'verified_source': 'admin',
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertFalse(res.data['is_global'])
        self.assertEqual(res.data['verified_source'], 'group')
        mock_pub.assert_called_once()

    def test_seed_global_catalog_and_include_global_query(self):
        call_command('seed_global_catalog')
        self.assertEqual(Product.objects.filter(is_global=True).count(), 25)

        res = self.user_client.get('/product-api/api/products/?group_id=1&include_global=true')
        self.assertEqual(res.status_code, 200)
        names = [p['name'] for p in res.data]
        self.assertIn('Produto Privado G1', names)
        self.assertIn('Café Tradicional 500g', names)
        self.assertNotIn('Produto Privado G2', names)

    def test_promote_global_requires_staff_permission(self):
        res_forbidden = self.user_client.post(
            f'/product-api/api/products/{self.p1.id}/promote-global/',
            {},
            format='json',
        )
        self.assertEqual(res_forbidden.status_code, status.HTTP_403_FORBIDDEN)

        res_ok = self.staff_client.post(
            f'/product-api/api/products/{self.p1.id}/promote-global/',
            {'verified_source': 'admin'},
            format='json',
        )
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)
        self.p1.refresh_from_db()
        self.assertTrue(self.p1.is_global)
        self.assertEqual(self.p1.verified_source, 'admin')

    def test_group_deleted_consumer_preserves_global_products(self):
        self.p1.is_global = True
        self.p1.save(update_fields=['is_global'])
        temp = Product.objects.create(group_id='1', name='Temporário G1', added_by='1', is_global=False)

        handle_event('group.deleted', {'group_id': 1})
        self.assertFalse(Product.objects.filter(id=temp.id).exists())
        self.assertTrue(Product.objects.filter(id=self.p1.id).exists())
        self.assertTrue(Product.objects.filter(id=self.p2.id).exists())

    def test_all_groups_requires_staff_permission(self):
        res_user = self.user_client.get('/product-api/api/products/?all_groups=true')
        self.assertEqual(res_user.status_code, 200)
        self.assertEqual(len(res_user.data), 0)

        res_staff = self.staff_client.get('/product-api/api/products/?all_groups=true')
        self.assertEqual(res_staff.status_code, 200)
        self.assertEqual(len(res_staff.data), 2)
