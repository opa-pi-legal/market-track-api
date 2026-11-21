from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from api.management.commands.consume_events import handle_event
from api.models import Market


class MarketApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=SimpleNamespace(id=1, is_authenticated=True))
        self.m1 = Market.objects.create(
            group_id='1',
            name='Atacadão Centro',
            city='São Paulo',
            latitude=-23.5505,
            longitude=-46.6333,
            added_by='1',
        )
        self.m2 = Market.objects.create(
            group_id='2',
            name='Assaí Outro Grupo',
            added_by='2',
        )

    def test_health_and_swagger_docs_public(self):
        anon = APIClient()
        self.assertEqual(anon.get('/market-api/health/').status_code, 200)
        self.assertEqual(anon.get('/market-api/docs/').status_code, 200)

    def test_group_isolation_on_list(self):
        res_empty = self.client.get('/market-api/api/market/')
        self.assertEqual(res_empty.status_code, 200)
        self.assertEqual(len(res_empty.data), 0)

        res_g1 = self.client.get('/market-api/api/market/?group_id=1')
        self.assertEqual(res_g1.status_code, 200)
        self.assertEqual([m['id'] for m in res_g1.data], [self.m1.id])

    @patch('api.views.publish_event')
    def test_create_market_with_geo_and_default_added_by(self, mock_pub):
        res = self.client.post(
            '/market-api/api/market/',
            {
                'group_id': '1',
                'name': 'Carrefour Paulista',
                'city': 'São Paulo',
                'latitude': -23.5614,
                'longitude': -46.6559,
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['added_by'], '1')
        self.assertEqual(res.data['city'], 'São Paulo')
        mock_pub.assert_called_once()

    def test_group_deleted_consumer_cleans_only_target_group(self):
        handle_event('group.deleted', {'group_id': 1})
        self.assertFalse(Market.objects.filter(group_id='1').exists())
        self.assertTrue(Market.objects.filter(group_id='2').exists())

    def test_all_groups_requires_staff_permission(self):
        res_user = self.client.get('/market-api/api/market/?all_groups=true')
        self.assertEqual(res_user.status_code, 200)
        self.assertEqual(len(res_user.data), 0)

        staff_client = APIClient()
        staff_client.force_authenticate(
            user=SimpleNamespace(id=99, is_authenticated=True, is_staff=True),
            token={'is_staff': True},
        )
        res_staff = staff_client.get('/market-api/api/market/?all_groups=true')
        self.assertEqual(res_staff.status_code, 200)
        self.assertEqual(len(res_staff.data), 2)
