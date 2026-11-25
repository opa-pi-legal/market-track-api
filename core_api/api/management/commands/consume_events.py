import json
import logging
import urllib.request
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Avg, Min
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from api.messaging import start_consumer
from api.models import (
    ActivityLog,
    CommunityOffer,
    Groups,
    OfferVote,
    PriceAlert,
    PriceRecord,
    ShoppingListItem,
    User,
    UserInGroup,
)

logger = logging.getLogger(__name__)


def _handle_offer_published(payload: dict) -> None:
    offer_id = payload.get('offer_id')
    offer = CommunityOffer.objects.filter(id=offer_id).first()
    if not offer:
        return

    prev_qs = CommunityOffer.objects.exclude(id=offer.id)
    if offer.ean:
        prev_qs = prev_qs.filter(ean=offer.ean)
    else:
        prev_qs = prev_qs.filter(product_name__iexact=offer.product_name)

    avg_val = prev_qs.aggregate(avg=Avg('price_cents'))['avg']
    if avg_val and avg_val > 0:
        ref_avg = int(round(avg_val))
        discount = (
            int(round((ref_avg - offer.price_cents) * 100 / ref_avg))
            if offer.price_cents < ref_avg
            else 0
        )
        offer.reference_avg_cents = ref_avg
        offer.discount_percent = max(0, discount)
        offer.save(update_fields=['reference_avg_cents', 'discount_percent', 'updated_at'])

    seen_groups = set()
    offer_name_lower = (offer.product_name or '').strip().lower()
    offer_ean = (offer.ean or '').strip()
    pending_items = ShoppingListItem.objects.filter(checked=False).select_related('shopping_list')
    for item in pending_items:
        item_name_lower = (item.product_name or '').strip().lower()
        matches_ean = bool(offer_ean and item.product_id and str(item.product_id).strip() == offer_ean)
        matches_name = bool(
            offer_name_lower
            and item_name_lower
            and (
                offer_name_lower in item_name_lower
                or (len(item_name_lower) >= 3 and item_name_lower in offer_name_lower)
            )
        )
        if not (matches_ean or matches_name):
            continue

        gid = item.shopping_list.group_id
        if gid in seen_groups:
            continue
        seen_groups.add(gid)

        valor = f'{offer.price_cents / 100:.2f}'.replace('.', ',')
        PriceAlert.objects.create(
            group_id=gid,
            offer=offer,
            ean=offer.ean,
            product_name=offer.product_name,
            market_name=offer.market_name,
            previous_price_cents=offer.reference_avg_cents,
            new_price_cents=offer.price_cents,
            discount_percent=offer.discount_percent,
            message=f'Menor preço encontrado: {offer.product_name} por R$ {valor} no {offer.market_name}!',
        )

    # Modo simulador (Staff): garante entrega de alerta via RabbitMQ aos usuários no app mobile
    if payload.get('broadcast_alert'):
        notified_user_ids = set(
            UserInGroup.objects.filter(group_id__in=seen_groups).values_list('user_id', flat=True)
        )
        valor = f'{offer.price_cents / 100:.2f}'.replace('.', ',')
        desc_txt = f' (-{offer.discount_percent}%)' if offer.discount_percent else ''
        msg = f'Menor preço encontrado: {offer.product_name} por R$ {valor}{desc_txt} no {offer.market_name}!'
        for uid in User.objects.filter(is_active=True).exclude(id__in=notified_user_ids).values_list('id', flat=True):
            PriceAlert.objects.create(
                user_id=uid,
                group=None,
                offer=offer,
                ean=offer.ean,
                product_name=offer.product_name,
                market_name=offer.market_name,
                previous_price_cents=offer.reference_avg_cents,
                new_price_cents=offer.price_cents,
                discount_percent=offer.discount_percent,
                message=msg,
            )


def _handle_offer_voted(payload: dict) -> None:
    offer_id = payload.get('offer_id')
    offer = CommunityOffer.objects.filter(id=offer_id).first()
    if not offer:
        return

    confirmations_count = OfferVote.objects.filter(offer=offer, vote_type='confirm').count()
    reports_count = OfferVote.objects.filter(offer=offer, vote_type='expired').count()
    offer.confirmations_count = confirmations_count
    offer.reports_count = reports_count
    trust_score = confirmations_count - reports_count
    if (reports_count >= 3 and reports_count > confirmations_count) or trust_score <= -2:
        offer.is_active = False
    offer.save(update_fields=['confirmations_count', 'reports_count', 'is_active', 'updated_at'])


def _handle_offer_flagged(payload: dict) -> None:
    offer_id = payload.get('offer_id')
    offer = CommunityOffer.objects.select_related('reported_by').filter(id=offer_id).first()
    if not offer:
        return

    abuse_count = OfferVote.objects.filter(offer=offer, vote_type='abuse').count()
    offer.abuse_reports_count = abuse_count

    reporter_id = payload.get('user_id')
    reporter_is_guardian = False
    if reporter_id:
        total_rep = (
            CommunityOffer.objects.filter(reported_by_id=reporter_id).count()
            + OfferVote.objects.filter(user_id=reporter_id, vote_type='confirm').count()
        )
        reporter_is_guardian = total_rep >= 10

    update_fields = ['abuse_reports_count', 'updated_at']
    if abuse_count >= 2 or payload.get('is_staff') or reporter_is_guardian:
        offer.is_active = False
        offer.moderation_status = 'flagged'
        update_fields.extend(['is_active', 'moderation_status'])

    offer.save(update_fields=update_fields)

    if offer.reported_by and not offer.reported_by.is_staff:
        bad_offers = CommunityOffer.objects.filter(
            reported_by=offer.reported_by,
            moderation_status__in=('flagged', 'removed'),
        ).count()
        if bad_offers >= 3 and not offer.reported_by.community_banned:
            offer.reported_by.community_banned = True
            offer.reported_by.save(update_fields=['community_banned', 'updated_at'])


def _resolve_remote_name(url: str) -> str:
    try:
        headers = {'Accept': 'application/json'}
        staff_user = User.objects.filter(is_active=True, is_staff=True).first() or User.objects.filter(is_active=True).first()
        if staff_user is not None:
            token = AccessToken.for_user(staff_user)
            headers['Authorization'] = f'Bearer {str(token)}'
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                if isinstance(data, dict):
                    return str(data.get('name') or '').strip()
    except Exception:
        return ''
    return ''


def _handle_price_recorded(payload: dict) -> None:
    group_id = payload.get('group_id')
    product_id = str(payload.get('product_id', '')).strip()
    market_id = str(payload.get('market_id', '')).strip()
    price_cents = int(payload.get('price_cents', 0))
    is_promotion = bool(payload.get('is_promotion', False))
    record_id = payload.get('record_id')

    if not group_id or not Groups.objects.filter(id=group_id).exists():
        return

    prev_qs = PriceRecord.objects.filter(group_id=group_id, product_id=product_id)
    if record_id is not None:
        prev_qs = prev_qs.exclude(id=record_id)

    prev_min = prev_qs.aggregate(min_p=Min('price_cents'))['min_p']
    if (prev_min is not None and price_cents < prev_min) or is_promotion:
        product_name = str(payload.get('product_name') or '').strip()
        if not product_name and product_id:
            product_name = (
                ShoppingListItem.objects.filter(product_id=product_id)
                .exclude(product_name='')
                .values_list('product_name', flat=True)
                .first()
                or CommunityOffer.objects.filter(ean=product_id)
                .exclude(product_name='')
                .values_list('product_name', flat=True)
                .first()
                or ''
            ).strip()
        if not product_name and product_id.isdigit():
            product_name = _resolve_remote_name(f'http://product-api:8004/api/product/{product_id}/')
        if not product_name:
            product_name = 'Produto'

        market_name = str(payload.get('market_name') or '').strip()
        if not market_name and market_id:
            market_name = (
                CommunityOffer.objects.filter(market_id=market_id)
                .exclude(market_name='')
                .values_list('market_name', flat=True)
                .first()
                or ''
            ).strip()
        if not market_name and market_id.isdigit():
            market_name = _resolve_remote_name(f'http://market-api:8002/api/market/{market_id}/')
        if not market_name:
            market_name = 'Supermercado'

        # Evita duplicação caso o mesmo registro gere CommunityOffer + PriceRecord na sequência
        recent_cutoff = timezone.now() - timedelta(seconds=60)
        already_alerted = PriceAlert.objects.filter(
            group_id=group_id,
            product_name__iexact=product_name,
            new_price_cents=price_cents,
            created_at__gte=recent_cutoff,
        ).exists()
        if already_alerted:
            return

        discount = (
            int(round((prev_min - price_cents) * 100 / prev_min))
            if prev_min and price_cents < prev_min
            else 0
        )
        valor = f'{price_cents / 100:.2f}'.replace('.', ',')
        PriceAlert.objects.create(
            group_id=group_id,
            product_name=product_name,
            market_name=market_name,
            previous_price_cents=prev_min,
            new_price_cents=price_cents,
            discount_percent=max(0, discount),
            message=f'Menor preço registrado: {product_name} por R$ {valor} em {market_name}!',
        )


def _handle_activity(routing_key: str, payload: dict) -> None:
    group_id = payload.get('group_id')
    if not group_id or not Groups.objects.filter(id=group_id).exists():
        return

    entity_id = payload.get('entity_id')
    ActivityLog.objects.create(
        group_id=group_id,
        user_id=payload.get('user_id'),
        action=routing_key,
        entity_type=payload.get('entity_type', 'unknown'),
        entity_id=str(entity_id) if entity_id is not None else None,
        description=payload.get('description', ''),
    )


def handle_event(routing_key: str, payload: dict) -> None:
    if routing_key == 'offer.published':
        _handle_offer_published(payload)
    elif routing_key == 'offer.voted':
        _handle_offer_voted(payload)
    elif routing_key == 'offer.flagged':
        _handle_offer_flagged(payload)
    elif routing_key == 'price.recorded':
        _handle_price_recorded(payload)
    elif routing_key.startswith('activity.'):
        _handle_activity(routing_key, payload)


class Command(BaseCommand):
    help = 'Consume RabbitMQ events for core_api'

    def handle(self, *args, **options):
        start_consumer(
            queue_name='core_api.events',
            binding_keys=['offer.published', 'offer.voted', 'offer.flagged', 'price.recorded', 'activity.#'],
            handler_fn=handle_event,
        )
