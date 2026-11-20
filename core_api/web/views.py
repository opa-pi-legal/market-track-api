import json
import uuid
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from api.messaging import publish_event
from api.moderation import (
    DAILY_OFFER_LIMIT,
    bounding_box,
    contains_inappropriate_content,
    haversine_km,
    is_valid_ean,
    validate_price_cents,
)
from api.models import (
    ActivityLog,
    CommunityOffer,
    GroupInvite,
    Groups,
    OfferVote,
    PriceAlert,
    PriceRecord,
    ShoppingList,
    ShoppingListItem,
    User,
    UserInGroup,
)
from . import services


def _get_user_groups(user):
    return list(Groups.objects.filter(members__user=user).distinct().order_by('name'))


def _get_active_group(request):
    groups = _get_user_groups(request.user)
    if not groups:
        return None, groups

    active = request.user.last_active_group
    if active and any(g.id == active.id for g in groups):
        return active, groups

    active = groups[0]
    request.user.last_active_group = active
    request.user.last_active_group_updated_at = timezone.now()
    request.user.save(update_fields=['last_active_group', 'last_active_group_updated_at'])
    return active, groups


def _unread_alerts_queryset(user, group):
    qs = PriceAlert.objects.filter(
        Q(user=user) | Q(group__members__user=user),
        is_read=False,
    ).distinct()
    if group:
        qs = qs.filter(Q(group=group) | Q(user=user, group__isnull=True))
    return qs.order_by('-created_at')


def _base_context(request, active_nav: str):
    active_group, user_groups = _get_active_group(request)
    unread_alerts = list(_unread_alerts_queryset(request.user, active_group)[:10])
    return {
        'active_nav': active_nav,
        'active_group': active_group,
        'user_groups': user_groups,
        'unread_alerts_count': len(unread_alerts),
        'unread_alerts': unread_alerts,
    }


def _parse_money_to_cents(raw: str) -> int | None:
    cleaned = (raw or '').strip().replace('R$', '').replace(' ', '')
    if not cleaned:
        return None
    if ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace('.', '').replace(',', '.')
    elif ',' in cleaned:
        cleaned = cleaned.replace(',', '.')
    try:
        val = Decimal(cleaned)
        if val < 0:
            return None
        return int((val * 100).quantize(Decimal('1')))
    except (InvalidOperation, ValueError):
        return None


def _compute_basket_comparison(shopping_list: ShoppingList, group: Groups | None):
    items = list(shopping_list.items.all().order_by('checked', 'created_at'))
    if not items:
        return {'items_count': 0, 'markets': [], 'best_single': None, 'split_total_cents': 0, 'split_savings_cents': 0}

    offers = list(
        CommunityOffer.objects.filter(is_active=True, moderation_status='approved')
        .order_by('price_cents')
    )
    market_totals: dict[str, dict] = defaultdict(lambda: {'total_cents': 0, 'matched': 0})
    split_total = 0
    split_matched = 0

    for item in items:
        qty = float(item.quantity or 1)
        name_l = (item.product_name or '').strip().lower()
        ean = (item.product_id or '').strip()

        matched_offers = []
        for off in offers:
            if ean and off.ean and off.ean == ean:
                matched_offers.append(off)
            elif name_l and (
                name_l in off.product_name.lower()
                or (len(off.product_name) >= 3 and off.product_name.lower() in name_l)
            ):
                matched_offers.append(off)

        best_per_market: dict[str, int] = {}
        for off in matched_offers:
            m = off.market_name
            if m not in best_per_market or off.price_cents < best_per_market[m]:
                best_per_market[m] = off.price_cents

        if best_per_market:
            min_price = min(best_per_market.values())
            split_total += int(round(min_price * qty))
            split_matched += 1
            for m, p in best_per_market.items():
                market_totals[m]['total_cents'] += int(round(p * qty))
                market_totals[m]['matched'] += 1
        elif item.selected_price_cents:
            est = int(round(item.selected_price_cents * qty))
            split_total += est
            split_matched += 1
            if item.selected_market:
                market_totals[item.selected_market]['total_cents'] += est
                market_totals[item.selected_market]['matched'] += 1

    ranked = sorted(
        [
            {
                'market_name': name,
                'total_cents': info['total_cents'],
                'total_brl': f"{info['total_cents'] / 100:.2f}".replace('.', ','),
                'matched': info['matched'],
                'coverage': int(round((info['matched'] / len(items)) * 100)),
            }
            for name, info in market_totals.items()
        ],
        key=lambda x: (-x['matched'], x['total_cents']),
    )

    best_single = ranked[0] if ranked else None
    savings = 0
    if best_single and split_matched == best_single['matched'] and best_single['total_cents'] > split_total:
        savings = best_single['total_cents'] - split_total

    return {
        'items_count': len(items),
        'markets': ranked[:6],
        'best_single': best_single,
        'split_matched': split_matched,
        'split_total_cents': split_total,
        'split_total_brl': f'{split_total / 100:.2f}'.replace('.', ','),
        'split_savings_cents': savings,
        'split_savings_brl': f'{savings / 100:.2f}'.replace('.', ','),
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return redirect('web:dashboard')

    if request.method == 'POST':
        identifier = (request.POST.get('identifier') or '').strip()
        password = request.POST.get('password') or ''
        user = authenticate(request, username=identifier, password=password)
        if not user and '@' in identifier:
            found = User.objects.filter(email__iexact=identifier).first()
            if found:
                user = authenticate(request, username=found.username, password=password)
        if user:
            login(request, user)
            return redirect('web:dashboard')
        messages.error(request, 'E-mail/usuário ou senha inválidos.')

    return render(request, 'web/login.html', {'mode': 'login'})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('web:dashboard')

    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        email = (request.POST.get('email') or '').strip().lower()
        password = request.POST.get('password') or ''

        if not username or not email or len(password) < 6:
            messages.error(request, 'Preencha nome, e-mail e uma senha de pelo menos 6 caracteres.')
        elif User.objects.filter(Q(email__iexact=email) | Q(username__iexact=username)).exists():
            messages.error(request, 'Já existe uma conta com este usuário ou e-mail.')
        else:
            user = User.objects.create_user(username=username, email=email, password=password)
            login(request, user)
            messages.success(request, 'Conta criada com sucesso! Crie ou entre em um grupo para começar.')
            return redirect('web:dashboard')

    return render(request, 'web/login.html', {'mode': 'register'})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('web:login')


# ---------------------------------------------------------------------------
# Groups & Alerts
# ---------------------------------------------------------------------------

@login_required(login_url='/login/')
@require_POST
def select_group_view(request, group_id: int):
    group = get_object_or_404(Groups, id=group_id, members__user=request.user)
    request.user.last_active_group = group
    request.user.last_active_group_updated_at = timezone.now()
    request.user.save(update_fields=['last_active_group', 'last_active_group_updated_at'])
    return redirect(request.META.get('HTTP_REFERER') or 'web:dashboard')


@login_required(login_url='/login/')
@require_POST
def create_group_view(request):
    name = (request.POST.get('name') or '').strip()
    description = (request.POST.get('description') or '').strip()
    if not name:
        messages.error(request, 'Informe um nome para o grupo.')
        return redirect(request.META.get('HTTP_REFERER') or 'web:dashboard')

    group = Groups.objects.create(name=name, description=description)
    UserInGroup.objects.create(group=group, user=request.user, role='admin', is_admin=True)
    request.user.last_active_group = group
    request.user.last_active_group_updated_at = timezone.now()
    request.user.save(update_fields=['last_active_group', 'last_active_group_updated_at'])
    messages.success(request, f'Grupo "{group.name}" criado e ativado.')
    return redirect(request.META.get('HTTP_REFERER') or 'web:dashboard')


@login_required(login_url='/login/')
@require_POST
def join_group_view(request):
    code = (request.POST.get('code') or '').strip().upper()
    invite = GroupInvite.objects.select_related('group').filter(code__iexact=code, active=True).first()
    if not invite:
        messages.error(request, 'Código de convite inválido ou expirado.')
        return redirect(request.META.get('HTTP_REFERER') or 'web:dashboard')

    UserInGroup.objects.get_or_create(
        group=invite.group,
        user=request.user,
        defaults={'role': 'member', 'is_admin': False},
    )
    request.user.last_active_group = invite.group
    request.user.last_active_group_updated_at = timezone.now()
    request.user.save(update_fields=['last_active_group', 'last_active_group_updated_at'])
    messages.success(request, f'Você entrou no grupo "{invite.group.name}".')
    return redirect(request.META.get('HTTP_REFERER') or 'web:dashboard')


@login_required(login_url='/login/')
@require_POST
def create_invite_view(request):
    active_group, _ = _get_active_group(request)
    if not active_group:
        return redirect('web:catalog')
    code = uuid.uuid4().hex[:8].upper()
    GroupInvite.objects.create(code=code, group=active_group, created_by=request.user, active=True)
    messages.success(request, f'Novo convite gerado: {code}')
    return redirect('/catalogo/?tab=grupo')


@login_required(login_url='/login/')
def alerts_badge_partial(request):
    active_group, _ = _get_active_group(request)
    count = _unread_alerts_queryset(request.user, active_group).count()
    if count <= 0:
        return HttpResponse('')
    return HttpResponse(
        f'<span class="ml-auto inline-flex items-center justify-center rounded-full bg-rose-500 px-2 py-0.5 text-xs font-bold text-white">{count}</span>'
    )


@login_required(login_url='/login/')
@require_POST
def mark_alert_read_view(request, alert_id: int):
    alert = get_object_or_404(
        PriceAlert.objects.filter(Q(user=request.user) | Q(group__members__user=request.user)).distinct(),
        id=alert_id,
    )
    alert.is_read = True
    alert.save(update_fields=['is_read'])
    if request.headers.get('HX-Request'):
        return HttpResponse('')
    return redirect(request.META.get('HTTP_REFERER') or 'web:dashboard')


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required(login_url='/login/')
def dashboard_view(request):
    ctx = _base_context(request, 'dashboard')
    group = ctx['active_group']

    lists_qs = ShoppingList.objects.filter(group=group) if group else ShoppingList.objects.none()
    items_qs = ShoppingListItem.objects.filter(shopping_list__group=group) if group else ShoppingListItem.objects.none()
    offers_qs = CommunityOffer.objects.filter(is_active=True, moderation_status='approved')
    activities = list(ActivityLog.objects.filter(group=group).order_by('-created_at')[:12]) if group else []

    total_estimated_cents = 0
    total_budget_cents = 0
    for sl in lists_qs.filter(status='active'):
        if sl.budget_cents:
            total_budget_cents += sl.budget_cents
    for it in items_qs:
        unit_price = it.paid_price_cents or it.selected_price_cents or 0
        total_estimated_cents += int(round(unit_price * float(it.quantity or 1)))

    # Gráfico 1: média de preço por mercado na comunidade (top 6)
    market_stats = list(
        offers_qs.values('market_name')
        .annotate(avg_price=Avg('price_cents'), total_offers=Count('id'))
        .order_by('-total_offers')[:6]
    )
    chart_markets = {
        'labels': [m['market_name'] for m in market_stats],
        'avg_prices': [round((m['avg_price'] or 0) / 100, 2) for m in market_stats],
        'counts': [m['total_offers'] for m in market_stats],
    }

    # Gráfico 2: ofertas por categoria
    cat_stats = list(
        offers_qs.values('category')
        .annotate(total=Count('id'))
        .order_by('-total')[:6]
    )
    chart_categories = {
        'labels': [c['category'] or 'Geral' for c in cat_stats],
        'counts': [c['total'] for c in cat_stats],
    }

    # Gamificação do usuário
    offers_shared = CommunityOffer.objects.filter(reported_by=request.user).count()
    confirmations = OfferVote.objects.filter(user=request.user, vote_type='confirm').count()
    score = offers_shared + confirmations
    level = 'Guardião do Preço' if score >= 10 else ('Caçador de Ofertas' if score >= 3 else 'Explorador')

    top_offers = list(offers_qs.order_by('-discount_percent', '-created_at')[:5])
    for off in top_offers:
        off.price_brl = f'{off.price_cents / 100:.2f}'.replace('.', ',')

    ctx.update({
        'active_lists_count': lists_qs.filter(status='active').count(),
        'pending_items_count': items_qs.filter(checked=False).count(),
        'community_offers_count': offers_qs.count(),
        'total_estimated_brl': f'{total_estimated_cents / 100:.2f}'.replace('.', ','),
        'total_budget_brl': f'{total_budget_cents / 100:.2f}'.replace('.', ','),
        'top_offers': top_offers,
        'activities': activities,
        'user_level': level,
        'offers_shared': offers_shared,
        'confirmations_given': confirmations,
        'chart_markets_json': json.dumps(chart_markets),
        'chart_categories_json': json.dumps(chart_categories),
    })
    return render(request, 'web/dashboard.html', ctx)


# ---------------------------------------------------------------------------
# Shopping Lists (Split View + Basket Optimizer)
# ---------------------------------------------------------------------------

def _render_list_workspace(request, shopping_list: ShoppingList, group: Groups):
    items = list(shopping_list.items.all().order_by('checked', 'created_at'))
    for it in items:
        p = it.paid_price_cents or it.selected_price_cents
        it.price_brl = f'{p / 100:.2f}'.replace('.', ',') if p is not None else None
    estimated_cents = sum(
        int(round((it.paid_price_cents or it.selected_price_cents or 0) * float(it.quantity or 1)))
        for it in items
    )
    budget_pct = 0
    if shopping_list.budget_cents and shopping_list.budget_cents > 0:
        budget_pct = min(100, int(round((estimated_cents / shopping_list.budget_cents) * 100)))

    comparison = _compute_basket_comparison(shopping_list, group)
    return {
        'selected_list': shopping_list,
        'items': items,
        'estimated_cents': estimated_cents,
        'estimated_brl': f'{estimated_cents / 100:.2f}'.replace('.', ','),
        'budget_brl': f'{(shopping_list.budget_cents or 0) / 100:.2f}'.replace('.', ','),
        'budget_pct': budget_pct,
        'over_budget': bool(shopping_list.budget_cents and estimated_cents > shopping_list.budget_cents),
        'comparison': comparison,
    }


@login_required(login_url='/login/')
def lists_view(request):
    ctx = _base_context(request, 'lists')
    group = ctx['active_group']
    all_lists = list(ShoppingList.objects.filter(group=group).order_by('-created_at')) if group else []

    selected_id = request.GET.get('list')
    selected_list = None
    if selected_id and all_lists:
        selected_list = next((sl for sl in all_lists if str(sl.id) == str(selected_id)), None)
    if not selected_list and all_lists:
        selected_list = all_lists[0]

    ctx['all_lists'] = all_lists
    if selected_list and group:
        ctx.update(_render_list_workspace(request, selected_list, group))
    return render(request, 'web/lists.html', ctx)


@login_required(login_url='/login/')
@require_POST
def create_list_view(request):
    active_group, _ = _get_active_group(request)
    if not active_group:
        messages.error(request, 'Crie ou selecione um grupo antes de criar uma lista.')
        return redirect('web:lists')

    name = (request.POST.get('name') or '').strip()
    budget_cents = _parse_money_to_cents(request.POST.get('budget') or '')
    if not name:
        messages.error(request, 'Informe o nome da lista.')
        return redirect('web:lists')

    sl = ShoppingList.objects.create(
        group=active_group,
        name=name,
        owner=request.user,
        budget_cents=budget_cents,
    )
    publish_event(
        'activity.list_created',
        {
            'group_id': active_group.id,
            'user_id': str(request.user.id),
            'entity_type': 'shopping_list',
            'entity_id': str(sl.id),
            'description': f'Lista "{sl.name}" criada via Web',
        },
    )
    return redirect(f'/listas/?list={sl.id}')


@login_required(login_url='/login/')
@require_POST
def update_list_budget_view(request, list_id: int):
    active_group, _ = _get_active_group(request)
    sl = get_object_or_404(ShoppingList, id=list_id, group=active_group)
    sl.budget_cents = _parse_money_to_cents(request.POST.get('budget') or '')
    sl.save(update_fields=['budget_cents', 'updated_at'])
    if request.headers.get('HX-Request'):
        return render(request, 'web/partials/list_workspace.html', _render_list_workspace(request, sl, active_group))
    return redirect(f'/listas/?list={sl.id}')


@login_required(login_url='/login/')
@require_POST
def add_list_item_view(request, list_id: int):
    active_group, _ = _get_active_group(request)
    sl = get_object_or_404(ShoppingList, id=list_id, group=active_group)
    product_name = (request.POST.get('product_name') or '').strip()
    qty_raw = (request.POST.get('quantity') or '1').replace(',', '.')
    unit = (request.POST.get('unit') or 'un').strip() or 'un'
    price_cents = _parse_money_to_cents(request.POST.get('price') or '')
    market = (request.POST.get('market') or '').strip() or None

    try:
        qty = Decimal(qty_raw)
        if qty <= 0:
            qty = Decimal('1')
    except InvalidOperation:
        qty = Decimal('1')

    if product_name:
        ShoppingListItem.objects.create(
            shopping_list=sl,
            product_name=product_name,
            quantity=qty,
            unit=unit,
            selected_price_cents=price_cents,
            selected_market=market,
            added_by=str(request.user.id),
        )
    if request.headers.get('HX-Request'):
        return render(request, 'web/partials/list_workspace.html', _render_list_workspace(request, sl, active_group))
    return redirect(f'/listas/?list={sl.id}')


@login_required(login_url='/login/')
@require_POST
def toggle_list_item_view(request, item_id: int):
    active_group, _ = _get_active_group(request)
    item = get_object_or_404(ShoppingListItem, id=item_id, shopping_list__group=active_group)
    item.checked = not item.checked
    item.save(update_fields=['checked', 'updated_at'])
    if request.headers.get('HX-Request'):
        return render(
            request,
            'web/partials/list_workspace.html',
            _render_list_workspace(request, item.shopping_list, active_group),
        )
    return redirect(f'/listas/?list={item.shopping_list_id}')


@login_required(login_url='/login/')
@require_POST
def delete_list_item_view(request, item_id: int):
    active_group, _ = _get_active_group(request)
    item = get_object_or_404(ShoppingListItem, id=item_id, shopping_list__group=active_group)
    sl = item.shopping_list
    item.delete()
    if request.headers.get('HX-Request'):
        return render(request, 'web/partials/list_workspace.html', _render_list_workspace(request, sl, active_group))
    return redirect(f'/listas/?list={sl.id}')


# ---------------------------------------------------------------------------
# Community Radar (Table + Configurable Radius + Moderation Actions)
# ---------------------------------------------------------------------------

def _query_community_offers(request, active_group):
    scope = (request.GET.get('scope') or 'community').strip().lower()
    q = (request.GET.get('q') or '').strip()
    category = (request.GET.get('category') or '').strip()
    sort = (request.GET.get('sort') or 'discount').strip().lower()
    radius_param = (request.GET.get('radius_km') or '').strip().lower()

    lat_raw = request.GET.get('lat') or request.session.get('user_lat')
    lng_raw = request.GET.get('lng') or request.session.get('user_lng')
    lat = lng = None
    if lat_raw and lng_raw:
        try:
            lat = float(lat_raw)
            lng = float(lng_raw)
            request.session['user_lat'] = lat
            request.session['user_lng'] = lng
        except ValueError:
            lat = lng = None

    if radius_param in ('all', '0', 'sem_limite'):
        radius_km = None
        selected_radius_str = 'all'
    elif radius_param:
        try:
            val = float(radius_param.replace(',', '.'))
            radius_km = max(1.0, min(500.0, val))
            selected_radius_str = str(int(radius_km)) if radius_km.is_integer() else str(radius_km)
        except ValueError:
            pref = request.user.preferred_radius_km
            radius_km = float(pref) if pref else None
            selected_radius_str = str(pref) if pref else 'all'
    else:
        pref = request.user.preferred_radius_km
        radius_km = float(pref) if pref else None
        selected_radius_str = str(pref) if pref else 'all'

    qs = CommunityOffer.objects.select_related('reported_by').filter(
        is_active=True,
        moderation_status='approved',
    )
    if scope == 'group' and active_group:
        qs = qs.filter(group=active_group)
    if category:
        qs = qs.filter(category__iexact=category)
    if q:
        qs = qs.filter(
            Q(product_name__icontains=q)
            | Q(brand__icontains=q)
            | Q(market_name__icontains=q)
            | Q(city__icontains=q)
            | Q(ean__icontains=q)
        )

    if lat is not None and lng is not None and radius_km is not None:
        min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, radius_km)
        qs = qs.filter(
            Q(latitude__gte=min_lat, latitude__lte=max_lat, longitude__gte=min_lng, longitude__lte=max_lng)
            | Q(latitude__isnull=True)
            | Q(longitude__isnull=True)
        )

    if sort == 'price':
        qs = qs.order_by('price_cents', '-created_at')
    elif sort == 'recent':
        qs = qs.order_by('-created_at')
    elif sort == 'confirmed':
        qs = qs.order_by('-confirmations_count', '-created_at')
    else:
        qs = qs.order_by('-discount_percent', '-confirmations_count', '-created_at')

    offers = list(qs[:100])
    user_votes = dict(
        OfferVote.objects.filter(user=request.user, offer__in=offers).values_list('offer_id', 'vote_type')
    )

    filtered = []
    for off in offers:
        off.my_vote = user_votes.get(off.id)
        off.price_brl = f'{off.price_cents / 100:.2f}'.replace('.', ',')
        off.distance_km = None
        if lat is not None and lng is not None and off.latitude is not None and off.longitude is not None:
            dist = haversine_km(lat, lng, off.latitude, off.longitude)
            if radius_km is not None and dist > radius_km:
                continue
            off.distance_km = round(dist, 1)
        filtered.append(off)

    if sort == 'distance' and lat is not None and lng is not None:
        filtered.sort(key=lambda o: (o.distance_km is None, o.distance_km or 9999))

    return {
        'offers': filtered,
        'scope': scope,
        'q': q,
        'category': category,
        'sort': sort,
        'lat': lat,
        'lng': lng,
        'selected_radius': selected_radius_str,
        'radius_presets': ['5', '10', '30', '50'],
    }


@login_required(login_url='/login/')
def community_view(request):
    ctx = _base_context(request, 'community')
    group = ctx['active_group']
    ctx.update(_query_community_offers(request, group))
    ctx['user_lists'] = list(ShoppingList.objects.filter(group=group, status='active')) if group else []
    ctx['categories'] = ['Mercearia', 'Laticínios', 'Bebidas', 'Limpeza', 'Higiene', 'Hortifruti', 'Carnes', 'Geral']

    if request.headers.get('HX-Request'):
        return render(request, 'web/partials/community_table.html', ctx)
    return render(request, 'web/community.html', ctx)


@login_required(login_url='/login/')
@require_POST
def save_radius_preference_view(request):
    raw = (request.POST.get('radius_km') or '').strip().lower()
    if raw in ('all', '0', 'sem_limite', ''):
        request.user.preferred_radius_km = None
        request.user.save(update_fields=['preferred_radius_km'])
        messages.success(request, 'Raio da comunidade definido para: Sem limite.')
    else:
        try:
            val = int(round(float(raw.replace(',', '.'))))
            if 1 <= val <= 500:
                request.user.preferred_radius_km = val
                request.user.save(update_fields=['preferred_radius_km'])
                messages.success(request, f'Raio preferido atualizado para {val} km.')
            else:
                messages.error(request, 'Informe um raio entre 1 e 500 km.')
        except ValueError:
            messages.error(request, 'Valor de raio inválido.')
    return redirect(request.META.get('HTTP_REFERER') or 'web:community')


@login_required(login_url='/login/')
@require_POST
def publish_offer_view(request):
    active_group, _ = _get_active_group(request)
    product_name = (request.POST.get('product_name') or '').strip()
    brand = (request.POST.get('brand') or '').strip()
    category = (request.POST.get('category') or 'Geral').strip()
    market_name = (request.POST.get('market_name') or '').strip()
    city = (request.POST.get('city') or '').strip()
    ean = (request.POST.get('ean') or '').strip()
    price_cents = _parse_money_to_cents(request.POST.get('price') or '')
    only_group = request.POST.get('only_group') == '1'

    lat_raw = (request.POST.get('latitude') or '').strip()
    lng_raw = (request.POST.get('longitude') or '').strip()
    lat = lng = None
    if lat_raw and lng_raw:
        try:
            lat = float(lat_raw.replace(',', '.'))
            lng = float(lng_raw.replace(',', '.'))
        except ValueError:
            lat = lng = None

    if request.user.community_banned and not only_group:
        messages.error(request, 'Sua conta está restrita para publicações na comunidade global.')
        return redirect('web:community')

    if not product_name or not market_name:
        messages.error(request, 'Informe pelo menos o nome do produto e o mercado.')
        return redirect('web:community')

    for text in (product_name, brand, market_name, city):
        if contains_inappropriate_content(text):
            messages.error(request, 'Conteúdo impróprio detectado. Revise o texto antes de publicar.')
            return redirect('web:community')

    ok_price, err_price = validate_price_cents(price_cents)
    if not ok_price:
        messages.error(request, err_price)
        return redirect('web:community')

    if ean and not is_valid_ean(ean):
        messages.error(request, 'Código de barras EAN inválido.')
        return redirect('web:community')

    if not request.user.is_staff:
        since = timezone.now() - timedelta(hours=24)
        if CommunityOffer.objects.filter(reported_by=request.user, created_at__gte=since).count() >= DAILY_OFFER_LIMIT:
            messages.error(request, f'Limite diário de {DAILY_OFFER_LIMIT} ofertas atingido.')
            return redirect('web:community')

    offer = CommunityOffer.objects.create(
        reported_by=request.user,
        group=active_group if only_group else None,
        ean=ean,
        product_name=product_name,
        brand=brand,
        category=category,
        market_name=market_name,
        city=city,
        latitude=lat,
        longitude=lng,
        price_cents=price_cents,
        is_promotion=True,
        is_active=True,
    )
    OfferVote.objects.get_or_create(offer=offer, user=request.user, defaults={'vote_type': 'confirm'})
    publish_event(
        'offer.published',
        {
            'offer_id': offer.id,
            'ean': offer.ean,
            'product_name': offer.product_name,
            'market_name': offer.market_name,
            'price_cents': offer.price_cents,
            'latitude': offer.latitude,
            'longitude': offer.longitude,
            'group_id': offer.group_id,
            'reported_by_id': request.user.id,
        },
    )
    messages.success(request, f'Oferta "{offer.product_name}" publicada e enviada para a fila RabbitMQ!')
    return redirect('web:community')


@login_required(login_url='/login/')
@require_POST
def vote_offer_view(request, offer_id: int):
    offer = get_object_or_404(CommunityOffer, id=offer_id)
    vote_type = (request.POST.get('vote_type') or '').strip().lower()
    if vote_type not in ('confirm', 'expired', 'abuse'):
        return redirect('web:community')

    OfferVote.objects.update_or_create(offer=offer, user=request.user, defaults={'vote_type': vote_type})
    offer.confirmations_count = OfferVote.objects.filter(offer=offer, vote_type='confirm').count()
    offer.reports_count = OfferVote.objects.filter(offer=offer, vote_type='expired').count()
    offer.abuse_reports_count = OfferVote.objects.filter(offer=offer, vote_type='abuse').count()
    fields = ['confirmations_count', 'reports_count', 'abuse_reports_count', 'updated_at']

    if vote_type == 'abuse' and (offer.abuse_reports_count >= 2 or request.user.is_staff):
        offer.is_active = False
        offer.moderation_status = 'flagged'
        fields.extend(['is_active', 'moderation_status'])

    offer.save(update_fields=fields)

    if vote_type == 'abuse':
        publish_event(
            'offer.flagged',
            {
                'offer_id': offer.id,
                'user_id': request.user.id,
                'is_staff': request.user.is_staff,
                'abuse_reports_count': offer.abuse_reports_count,
            },
        )
        messages.warning(request, 'Denúncia registrada. A oferta foi encaminhada para moderação.')
    else:
        publish_event(
            'offer.voted',
            {
                'offer_id': offer.id,
                'user_id': request.user.id,
                'vote_type': vote_type,
                'confirmations_count': offer.confirmations_count,
                'reports_count': offer.reports_count,
            },
        )

    return redirect(request.META.get('HTTP_REFERER') or 'web:community')


@login_required(login_url='/login/')
@require_POST
def add_offer_to_list_view(request, offer_id: int):
    active_group, _ = _get_active_group(request)
    offer = get_object_or_404(CommunityOffer, id=offer_id)
    list_id = request.POST.get('list_id')
    new_list_name = (request.POST.get('new_list_name') or '').strip()

    if not active_group:
        messages.error(request, 'Selecione um grupo primeiro.')
        return redirect('web:community')

    if new_list_name:
        sl = ShoppingList.objects.create(group=active_group, name=new_list_name, owner=request.user)
    else:
        sl = get_object_or_404(ShoppingList, id=list_id, group=active_group)

    ShoppingListItem.objects.create(
        shopping_list=sl,
        product_id=offer.ean or None,
        product_name=offer.product_name,
        quantity=Decimal('1'),
        unit='un',
        selected_market=offer.market_name,
        selected_price_cents=offer.price_cents,
        added_by=str(request.user.id),
    )
    messages.success(request, f'"{offer.product_name}" adicionado à lista "{sl.name}".')
    return redirect(request.META.get('HTTP_REFERER') or 'web:community')


# ---------------------------------------------------------------------------
# Catalog (Markets, Products + Global, Group Members/Invites)
# ---------------------------------------------------------------------------

@login_required(login_url='/login/')
def catalog_view(request):
    ctx = _base_context(request, 'catalog')
    group = ctx['active_group']
    tab = (request.GET.get('tab') or 'produtos').strip().lower()
    q = (request.GET.get('q') or '').strip()

    markets = services.fetch_markets(request.user, group.id) if group else []
    products = services.fetch_products(request.user, group.id, include_global=True, query=q) if group else []
    members = list(UserInGroup.objects.select_related('user').filter(group=group)) if group else []
    invites = list(GroupInvite.objects.filter(group=group, active=True).order_by('-created_at')[:5]) if group else []

    ctx.update({
        'tab': tab,
        'q': q,
        'markets': markets,
        'products': products,
        'members': members,
        'invites': invites,
    })
    return render(request, 'web/catalog.html', ctx)


@login_required(login_url='/login/')
@require_POST
def create_market_view(request):
    active_group, _ = _get_active_group(request)
    if not active_group:
        return redirect('web:catalog')

    name = (request.POST.get('name') or '').strip()
    brand = (request.POST.get('brand') or '').strip()
    address = (request.POST.get('address') or '').strip()
    city = (request.POST.get('city') or '').strip()
    lat_raw = (request.POST.get('latitude') or '').strip()
    lng_raw = (request.POST.get('longitude') or '').strip()

    payload = {
        'group_id': str(active_group.id),
        'name': name,
        'brand': brand,
        'address': address,
        'city': city,
        'added_by': str(request.user.id),
    }
    if lat_raw and lng_raw:
        try:
            payload['latitude'] = float(lat_raw.replace(',', '.'))
            payload['longitude'] = float(lng_raw.replace(',', '.'))
        except ValueError:
            pass

    ok, err = services.create_market(request.user, payload)
    if ok:
        messages.success(request, f'Mercado "{name}" cadastrado!')
    else:
        messages.error(request, f'Erro ao cadastrar mercado: {err}')
    return redirect('/catalogo/?tab=mercados')


@login_required(login_url='/login/')
@require_POST
def create_product_view(request):
    active_group, _ = _get_active_group(request)
    if not active_group:
        return redirect('web:catalog')

    name = (request.POST.get('name') or '').strip()
    brand = (request.POST.get('brand') or '').strip()
    category = (request.POST.get('category') or 'Geral').strip()
    barcode = (request.POST.get('barcode') or '').strip() or None
    unit = (request.POST.get('unit') or 'un').strip()

    payload = {
        'group_id': str(active_group.id),
        'name': name,
        'brand': brand or None,
        'category': category,
        'barcode': barcode,
        'unit': unit,
        'added_by': str(request.user.id),
    }
    ok, err = services.create_product(request.user, payload)
    if ok:
        messages.success(request, f'Produto "{name}" cadastrado no grupo!')
    else:
        messages.error(request, f'Erro ao cadastrar produto: {err}')
    return redirect('/catalogo/?tab=produtos')


# ---------------------------------------------------------------------------
# Staff Moderation Panel
# ---------------------------------------------------------------------------

@login_required(login_url='/login/')
def moderation_view(request):
    if not request.user.is_staff:
        return HttpResponseForbidden('Acesso restrito a moderadores.')

    ctx = _base_context(request, 'moderation')
    group = ctx['active_group']
    flagged_offers = list(
        CommunityOffer.objects.select_related('reported_by')
        .filter(moderation_status__in=('flagged', 'removed'))
        .order_by('-abuse_reports_count', '-updated_at')[:50]
    )
    for off in flagged_offers:
        off.price_brl = f'{off.price_cents / 100:.2f}'.replace('.', ',')

    group_products = [
        p for p in (services.fetch_products(request.user, group.id, include_global=False) if group else [])
        if not p.get('is_global')
    ]
    banned_users = list(User.objects.filter(community_banned=True).order_by('-updated_at')[:20])

    ctx.update({
        'flagged_offers': flagged_offers,
        'group_products': group_products,
        'banned_users': banned_users,
    })
    return render(request, 'web/moderation.html', ctx)


@login_required(login_url='/login/')
@require_POST
def moderate_offer_view(request, offer_id: int):
    if not request.user.is_staff:
        return HttpResponseForbidden('Acesso restrito a moderadores.')

    offer = get_object_or_404(CommunityOffer, id=offer_id)
    action = (request.POST.get('action') or '').strip().lower()
    if action == 'approve':
        offer.moderation_status = 'approved'
        offer.is_active = True
        offer.save(update_fields=['moderation_status', 'is_active', 'updated_at'])
        messages.success(request, f'Oferta #{offer.id} restaurada no feed.')
    elif action == 'remove':
        offer.moderation_status = 'removed'
        offer.is_active = False
        offer.save(update_fields=['moderation_status', 'is_active', 'updated_at'])
        messages.info(request, f'Oferta #{offer.id} removida definitivamente.')
    elif action == 'ban_author':
        offer.moderation_status = 'removed'
        offer.is_active = False
        offer.save(update_fields=['moderation_status', 'is_active', 'updated_at'])
        if offer.reported_by:
            offer.reported_by.community_banned = True
            offer.reported_by.save(update_fields=['community_banned', 'updated_at'])
        messages.warning(request, 'Oferta removida e autor bloqueado de publicações globais.')
    return redirect('web:moderation')


@login_required(login_url='/login/')
@require_POST
def promote_product_view(request, product_id: int):
    if not request.user.is_staff:
        return HttpResponseForbidden('Acesso restrito a moderadores.')

    ok, err = services.promote_product_global(request.user, product_id)
    if ok:
        messages.success(request, f'Produto #{product_id} promovido para o Catálogo Global!')
    else:
        messages.error(request, f'Não foi possível promover o produto: {err}')
    return redirect('web:moderation')
