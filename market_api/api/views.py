import math
import unicodedata

from django.db.models import Q
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .messaging import publish_event
from .models import Market
from .serializers import MarketSerializer


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * (math.sin(dlng / 2) ** 2)
    )
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def _normalize_text(value: str) -> str:
    raw = unicodedata.normalize('NFKD', (value or '').strip().lower())
    no_accents = ''.join(ch for ch in raw if not unicodedata.combining(ch))
    return ' '.join(''.join(ch if ch.isalnum() or ch.isspace() else ' ' for ch in no_accents).split())


def _is_similar_market(name_a: str, brand_a: str, name_b: str, brand_b: str) -> bool:
    na = _normalize_text(name_a)
    nb = _normalize_text(name_b)
    if na and nb and (na in nb or nb in na):
        return True
    ba = _normalize_text(brand_a)
    bb = _normalize_text(brand_b)
    if ba and bb and (ba in bb or bb in ba):
        return True
    return False


class MarketViewSet(viewsets.ModelViewSet):
    queryset = Market.objects.all()
    serializer_class = MarketSerializer

    def _is_staff_request(self) -> bool:
        return bool(
            getattr(self.request.user, 'is_staff', False)
            or (self.request.auth and self.request.auth.get('is_staff'))
        )

    def _parse_geo_params(self):
        lat_raw = self.request.query_params.get('lat')
        lng_raw = self.request.query_params.get('lng')
        radius_raw = (self.request.query_params.get('radius_km') or '').strip().lower()
        lat = lng = radius_km = None
        if lat_raw and lng_raw:
            try:
                lat = float(lat_raw)
                lng = float(lng_raw)
            except ValueError:
                lat = lng = None
        if radius_raw and radius_raw not in ('all', 'none', '0', 'sem_limite'):
            try:
                val = float(radius_raw.replace(',', '.'))
                if 0.5 <= val <= 500:
                    radius_km = val
            except ValueError:
                radius_km = None
        return lat, lng, radius_km

    def _find_canonical_duplicate(
        self,
        *,
        name: str,
        brand: str,
        city: str,
        osm_place_id: str,
        lat,
        lng,
    ):
        active_qs = Market.objects.filter(status='active')
        if osm_place_id:
            by_osm = active_qs.filter(osm_place_id=osm_place_id).first()
            if by_osm:
                return by_osm

        if lat is not None and lng is not None:
            # Delta ~0.002 graus ~220m para pré-filtrar no banco e confirmar com haversine <= 150m
            candidates = active_qs.filter(
                latitude__isnull=False,
                longitude__isnull=False,
                latitude__gte=lat - 0.0025,
                latitude__lte=lat + 0.0025,
                longitude__gte=lng - 0.0025,
                longitude__lte=lng + 0.0025,
            )
            for cand in candidates:
                dist = haversine_km(lat, lng, cand.latitude, cand.longitude)
                if dist <= 0.15 and _is_similar_market(name, brand, cand.name, cand.brand):
                    return cand

        if city:
            return active_qs.filter(name__iexact=name.strip(), city__iexact=city.strip()).first()
        return None

    def get_queryset(self):
        queryset = Market.objects.all()
        group_id = (self.request.query_params.get('group_id') or self.request.query_params.get('group') or '').strip()
        all_groups = self.request.query_params.get('all_groups', 'false').lower() in ('true', '1', 'yes')
        scope = (self.request.query_params.get('scope') or '').strip().lower()
        discover = self.request.query_params.get('discover', 'false').lower() in ('true', '1', 'yes')
        verified_only = self.request.query_params.get('verified_only', 'false').lower() in ('true', '1', 'yes')

        is_community_query = scope == 'community' or discover
        if self.action == 'list' and not group_id and not is_community_query and not (all_groups and self._is_staff_request()):
            return queryset.none()

        status_param = self.request.query_params.get('status') or ('active' if self.action == 'list' else None)
        q = (self.request.query_params.get('q') or '').strip()

        if status_param and status_param != 'all':
            queryset = queryset.filter(status=status_param)
        if verified_only:
            queryset = queryset.filter(is_verified=True)
        if is_community_query:
            queryset = queryset.filter(
                Q(is_verified=True)
                | Q(group_id='global')
                | (Q(latitude__isnull=False) & Q(longitude__isnull=False))
            )
        elif group_id and not (all_groups and self._is_staff_request()):
            matching_ids = [
                m.id
                for m in queryset
                if str(m.group_id) == str(group_id)
                or str(m.group_id) == 'global'
                or str(group_id) in [str(g) for g in (m.linked_group_ids or [])]
            ]
            queryset = queryset.filter(id__in=matching_ids)
        elif group_id and all_groups and self._is_staff_request():
            queryset = queryset.filter(group_id=str(group_id))

        if q:
            queryset = queryset.filter(
                Q(name__icontains=q)
                | Q(brand__icontains=q)
                | Q(city__icontains=q)
                | Q(address__icontains=q)
            )
        return queryset.order_by('-is_verified', '-created_at')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        lat, lng, radius_km = self._parse_geo_params()
        strict_geo = request.query_params.get('strict_geo', 'false').lower() in ('true', '1', 'yes')

        markets = list(queryset)
        if lat is not None and lng is not None:
            filtered = []
            for mkt in markets:
                if mkt.latitude is not None and mkt.longitude is not None:
                    dist = haversine_km(lat, lng, mkt.latitude, mkt.longitude)
                    mkt._distance_km = dist
                    if radius_km is None or dist <= radius_km:
                        filtered.append(mkt)
                elif not strict_geo:
                    mkt._distance_km = None
                    filtered.append(mkt)
            filtered.sort(
                key=lambda m: (
                    m._distance_km is None,
                    m._distance_km if m._distance_km is not None else 999999.0,
                    not m.is_verified,
                )
            )
            markets = filtered

        serializer = self.get_serializer(markets, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        raw_group = (data.get('group_id') or '').strip() or 'global'
        name = (data.get('name') or '').strip()
        brand = (data.get('brand') or '').strip()
        city = (data.get('city') or '').strip()
        address = (data.get('address') or '').strip()
        osm_place_id = (data.get('osm_place_id') or '').strip()
        lat = data.get('latitude')
        lng = data.get('longitude')
        if lat == 0 and lng == 0:
            lat = lng = None

        existing = self._find_canonical_duplicate(
            name=name,
            brand=brand,
            city=city,
            osm_place_id=osm_place_id,
            lat=lat,
            lng=lng,
        )
        if existing is not None:
            linked = [str(g) for g in (existing.linked_group_ids or []) if str(g).strip()]
            if existing.group_id and str(existing.group_id).strip().lower() != 'global' and str(existing.group_id) not in linked:
                linked.append(str(existing.group_id))
            if raw_group.lower() != 'global' and raw_group not in linked:
                linked.append(raw_group)
            existing.linked_group_ids = linked

            if not existing.city and city:
                existing.city = city
            if not existing.address and address:
                existing.address = address
            if existing.latitude is None and lat is not None:
                existing.latitude = lat
            if existing.longitude is None and lng is not None:
                existing.longitude = lng
            if not existing.osm_place_id and osm_place_id:
                existing.osm_place_id = osm_place_id
            if len(linked) >= 2 or self._is_staff_request():
                existing.is_verified = True
            existing.save()
            out = self.get_serializer(existing)
            return Response(out.data, status=status.HTTP_200_OK)

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        added_by = serializer.validated_data.get('added_by')
        user_id = getattr(self.request.user, 'id', None)
        if not added_by:
            added_by = str(user_id) if user_id is not None else 'admin'
        group_id = (serializer.validated_data.get('group_id') or '').strip() or 'global'
        linked = [str(g) for g in (serializer.validated_data.get('linked_group_ids') or []) if str(g).strip()]
        if group_id.lower() != 'global' and group_id not in linked:
            linked.append(group_id)
        is_verified = bool(serializer.validated_data.get('is_verified', False)) or self._is_staff_request() or len(linked) >= 2
        lat = serializer.validated_data.get('latitude')
        lng = serializer.validated_data.get('longitude')
        if lat == 0 and lng == 0:
            lat = lng = None

        instance = serializer.save(
            added_by=added_by,
            group_id=group_id,
            linked_group_ids=linked,
            is_verified=is_verified,
            latitude=lat,
            longitude=lng,
        )
        publish_event(
            'activity.market_created',
            {
                'group_id': str(instance.group_id),
                'user_id': str(user_id) if user_id is not None else added_by,
                'entity_type': 'market',
                'entity_id': str(instance.id),
                'description': f'Mercado "{instance.name}" cadastrado',
            },
        )

    @action(detail=True, methods=['post'], url_path='link-group')
    def link_group(self, request, pk=None):
        market = self.get_object()
        group_id = str(request.data.get('group_id') or request.data.get('group') or '').strip()
        if not group_id:
            return Response({'detail': 'group_id é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        linked = [str(g) for g in (market.linked_group_ids or []) if str(g).strip()]
        if market.group_id and str(market.group_id).strip().lower() != 'global' and str(market.group_id) not in linked:
            linked.append(str(market.group_id))
        if group_id.lower() != 'global' and group_id not in linked:
            linked.append(group_id)
        market.linked_group_ids = linked
        if len(linked) >= 2 or self._is_staff_request():
            market.is_verified = True
        market.save(update_fields=['linked_group_ids', 'is_verified'])
        return Response(self.get_serializer(market).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='verify')
    def verify(self, request, pk=None):
        if not self._is_staff_request():
            return Response(
                {'detail': 'Apenas moderadores Staff podem verificar mercados manualmente.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        market = self.get_object()
        market.is_verified = True
        market.save(update_fields=['is_verified'])
        return Response(self.get_serializer(market).data, status=status.HTTP_200_OK)


def health_check(request):
    return HttpResponse('OK', status=200)
