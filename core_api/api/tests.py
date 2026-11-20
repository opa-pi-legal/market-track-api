from unittest.mock import patch

from django.test import Client, TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from api.management.commands.consume_events import (
    _handle_offer_flagged,
    _handle_offer_published,
)
from api.models import (
    CommunityOffer,
    Groups,
    OfferVote,
    PriceAlert,
    ShoppingList,
    ShoppingListItem,
    User,
    UserInGroup,
)
from api.moderation import (
    contains_inappropriate_content,
    haversine_km,
    is_valid_ean,
    validate_price_cents,
)


class ModerationAndGeoUnitTests(TestCase):
    def test_profanity_and_leet_blocked_without_food_false_positives(self):
        self.assertTrue(contains_inappropriate_content('P1r0c@ gigante'))
        self.assertTrue(contains_inappropriate_content('p i r o c a'))
        self.assertFalse(contains_inappropriate_content('Café Pilão Tradicional 500g'))
        self.assertFalse(contains_inappropriate_content('Peito de Frango Congelado 1kg'))
        self.assertFalse(contains_inappropriate_content('Linguiça Toscana Aurora'))
        self.assertFalse(contains_inappropriate_content('Picolé de Coco'))

    def test_price_sanity_and_ean_validation(self):
        self.assertFalse(validate_price_cents(10)[0])
        self.assertFalse(validate_price_cents(999_999)[0])
        self.assertTrue(validate_price_cents(1290)[0])
        self.assertTrue(is_valid_ean('7896089011357'))
        self.assertFalse(is_valid_ean('1234567890123'))

    def test_haversine_distance_accuracy(self):
        # Sé -> Av. Paulista (~2.6 km)
        dist = haversine_km(-23.5505, -46.6333, -23.5614, -46.6559)
        self.assertAlmostEqual(dist, 2.6, delta=0.2)


class CoreApiSecurityAndCommunityTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(
            username='alice',
            email='alice@example.com',
            password='Password123!',
            first_name='Alice',
        )
        self.user_b = User.objects.create_user(
            username='bob',
            email='bob@example.com',
            password='Password123!',
            first_name='Bob',
        )
        self.staff = User.objects.create_user(
            username='mod',
            email='mod@example.com',
            password='Password123!',
            is_staff=True,
        )

        self.group_a = Groups.objects.create(name='Casa Alice')
        UserInGroup.objects.create(group=self.group_a, user=self.user_a, role='admin', is_admin=True)

        self.group_b = Groups.objects.create(name='Casa Bob')
        UserInGroup.objects.create(group=self.group_b, user=self.user_b, role='admin', is_admin=True)

        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)

        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

        self.client_staff = APIClient()
        self.client_staff.force_authenticate(user=self.staff)

    def test_health_and_swagger_docs_public(self):
        anon = APIClient()
        self.assertEqual(anon.get('/core-api/health/').status_code, 200)
        self.assertEqual(anon.get('/core-api/docs/').status_code, 200)

    def test_login_returns_jwt_with_is_staff_claim(self):
        anon = APIClient()
        res = anon.post(
            '/core-api/api/login/',
            {'email': 'mod@example.com', 'password': 'Password123!'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        token = AccessToken(res.data['access'])
        self.assertTrue(token.get('is_staff'))

    def test_group_and_shopping_list_isolation(self):
        sl_a = ShoppingList.objects.create(group=self.group_a, name='Lista Alice', owner=self.user_a)
        res_a = self.client_a.get(f'/core-api/api/shopping-lists/?group={self.group_a.id}')
        self.assertEqual(res_a.status_code, 200)
        self.assertEqual(len(res_a.data), 1)
        self.assertEqual(res_a.data[0]['id'], sl_a.id)

        # Usuário B não pode enxergar listas do grupo A
        res_b = self.client_b.get(f'/core-api/api/shopping-lists/?group={self.group_a.id}')
        self.assertEqual(res_b.status_code, 200)
        self.assertEqual(len(res_b.data), 0)

    @patch('api.views.publish_event')
    def test_community_offer_rejects_profanity_and_invalid_price(self, mock_pub):
        res_profanity = self.client_a.post(
            '/core-api/api/community-offers/',
            {
                'product_name': 'P1r0c@ falsa',
                'market_name': 'Atacadão',
                'price_cents': 1290,
            },
            format='json',
        )
        self.assertEqual(res_profanity.status_code, status.HTTP_400_BAD_REQUEST)
        mock_pub.assert_not_called()

        res_price = self.client_a.post(
            '/core-api/api/community-offers/',
            {
                'product_name': 'Café Pilão 500g',
                'market_name': 'Atacadão',
                'price_cents': 5,
            },
            format='json',
        )
        self.assertEqual(res_price.status_code, status.HTTP_400_BAD_REQUEST)

    def test_community_configurable_radius_filter(self):
        near = CommunityOffer.objects.create(
            reported_by=self.user_b,
            product_name='Café Perto',
            market_name='Atacadão Centro',
            price_cents=1290,
            latitude=-23.5614,
            longitude=-46.6559,
        )
        far = CommunityOffer.objects.create(
            reported_by=self.user_b,
            product_name='Café Longe',
            market_name='Mercado Campinas',
            price_cents=1190,
            latitude=-22.9056,
            longitude=-47.0608,
        )

        # Raio 30 km a partir do centro de SP: inclui "near" (~2.6 km) e exclui "far" (~84 km)
        res_30 = self.client_a.get(
            '/core-api/api/community-offers/?scope=community&lat=-23.5505&lng=-46.6333&radius_km=30&strict_geo=true'
        )
        ids_30 = [o['id'] for o in res_30.data]
        self.assertIn(near.id, ids_30)
        self.assertNotIn(far.id, ids_30)

        # Campo livre 120 km ou "all" inclui ambos
        res_120 = self.client_a.get(
            '/core-api/api/community-offers/?scope=community&lat=-23.5505&lng=-46.6333&radius_km=120&strict_geo=true'
        )
        ids_120 = [o['id'] for o in res_120.data]
        self.assertIn(near.id, ids_120)
        self.assertIn(far.id, ids_120)

    def test_rabbitmq_offer_published_calculates_discount_and_creates_alert(self):
        sl = ShoppingList.objects.create(group=self.group_a, name='Semana', owner=self.user_a)
        ShoppingListItem.objects.create(
            shopping_list=sl,
            product_id='7896089011357',
            product_name='Café Pilão 500g',
            checked=False,
        )
        CommunityOffer.objects.create(
            reported_by=self.user_b,
            ean='7896089011357',
            product_name='Café Pilão 500g',
            market_name='Carrefour',
            price_cents=2000,
        )
        promo = CommunityOffer.objects.create(
            reported_by=self.user_b,
            ean='7896089011357',
            product_name='Café Pilão 500g',
            market_name='Atacadão',
            price_cents=1500,
        )

        _handle_offer_published({'offer_id': promo.id})
        promo.refresh_from_db()
        self.assertEqual(promo.reference_avg_cents, 2000)
        self.assertEqual(promo.discount_percent, 25)
        self.assertTrue(PriceAlert.objects.filter(group=self.group_a, offer=promo).exists())

    def test_price_alert_includes_global_user_alerts_when_group_filtered(self):
        alert = PriceAlert.objects.create(
            user=self.user_a,
            group=None,
            product_name='Leite Piracanjuba 1L',
            market_name='Assaí',
            new_price_cents=419,
            message='Oferta global para você!',
        )
        res = self.client_a.get(f'/core-api/api/price-alerts/?group={self.group_a.id}&unread_only=true')
        self.assertEqual(res.status_code, 200)
        self.assertIn(alert.id, [a['id'] for a in res.data])

    @patch('api.views.publish_event')
    def test_abuse_quarantine_and_staff_moderation(self, mock_pub):
        offer = CommunityOffer.objects.create(
            reported_by=self.user_b,
            product_name='Produto Suspeito',
            market_name='Mercado X',
            price_cents=1000,
        )
        OfferVote.objects.create(offer=offer, user=self.user_a, vote_type='abuse')
        OfferVote.objects.create(offer=offer, user=self.staff, vote_type='abuse')

        _handle_offer_flagged({'offer_id': offer.id, 'user_id': self.staff.id, 'is_staff': True})
        offer.refresh_from_db()
        self.assertFalse(offer.is_active)
        self.assertEqual(offer.moderation_status, 'flagged')

        # Moderador pode restaurar ou remover
        res = self.client_staff.post(
            f'/core-api/api/community-offers/{offer.id}/moderate/',
            {'action': 'approve'},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        offer.refresh_from_db()
        self.assertTrue(offer.is_active)
        self.assertEqual(offer.moderation_status, 'approved')


class WebAppSmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='webuser',
            email='web@example.com',
            password='Password123!',
        )
        self.staff = User.objects.create_user(
            username='webstaff',
            email='staff@example.com',
            password='Password123!',
            is_staff=True,
        )
        self.group = Groups.objects.create(name='Grupo Web')
        UserInGroup.objects.create(group=self.group, user=self.user, role='admin', is_admin=True)
        UserInGroup.objects.create(group=self.group, user=self.staff, role='admin', is_admin=True)

    @patch('web.views.services.fetch_products', return_value=[])
    @patch('web.views.publish_event')
    def test_web_pages_and_moderation_permissions(self, mock_pub, mock_fetch):
        c = Client()
        self.assertEqual(c.get('/login/').status_code, 200)
        self.assertEqual(c.get('/').status_code, 302)

        c.force_login(self.user)
        self.assertEqual(c.get('/').status_code, 200)
        self.assertEqual(c.get('/listas/').status_code, 200)
        self.assertEqual(c.get('/comunidade/?radius_km=25').status_code, 200)
        # Usuário comum não acessa moderação
        self.assertEqual(c.get('/moderacao/').status_code, 403)

        # Staff acessa moderação
        c.force_login(self.staff)
        self.assertEqual(c.get('/moderacao/').status_code, 200)
