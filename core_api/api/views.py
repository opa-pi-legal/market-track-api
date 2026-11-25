import uuid
from datetime import timedelta
from django.db.models import F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .messaging import publish_event
from .moderation import DAILY_OFFER_LIMIT, bounding_box, haversine_km
from .models import (
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
from .serializers import (
    ActivityLogSerializer,
    CommunityOfferSerializer,
    GroupInviteSerializer,
    GroupSerializer,
    PriceAlertSerializer,
    PriceRecordSerializer,
    RegisterSerializer,
    ShoppingListItemSerializer,
    ShoppingListSerializer,
    UserInGroupSerializer,
    UserSerializer,
)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_queryset(self):
        queryset = User.objects.all()
        email = self.request.query_params.get('email')
        username = self.request.query_params.get('username')
        if email:
            queryset = queryset.filter(email__iexact=email.strip())
        if username:
            queryset = queryset.filter(username__iexact=username.strip())
        return queryset

    def perform_update(self, serializer):
        if 'last_active_group' in serializer.validated_data:
            serializer.save(last_active_group_updated_at=timezone.now())
        else:
            serializer.save()

    @action(detail=False, methods=['get', 'patch'], url_path='me', permission_classes=[IsAuthenticated])
    def me(self, request):
        user = request.user
        if request.method == 'GET':
            return Response(UserSerializer(user).data, status=status.HTTP_200_OK)

        serializer = UserSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if 'last_active_group' in serializer.validated_data:
            serializer.save(last_active_group_updated_at=timezone.now())
        else:
            serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='staff', permission_classes=[IsAuthenticated, IsAdminUser])
    def staff_list(self, request):
        staff_qs = User.objects.filter(is_staff=True).order_by('-date_joined')
        return Response(UserSerializer(staff_qs, many=True).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='create-staff', permission_classes=[IsAuthenticated, IsAdminUser])
    def create_staff(self, request):
        email = (request.data.get('email') or '').strip().lower()
        username = (request.data.get('username') or '').strip()
        password = request.data.get('password') or ''

        if not email or '@' not in email:
            return Response(
                {'detail': 'Informe um e-mail válido para a conta Staff.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            existing.is_staff = True
            update_fields = ['is_staff']
            if username and existing.username != username and not User.objects.filter(username__iexact=username).exclude(pk=existing.pk).exists():
                existing.username = username
                update_fields.append('username')
            if password:
                if len(password) < 6:
                    return Response(
                        {'detail': 'A senha deve ter pelo menos 6 caracteres.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                existing.set_password(password)
                update_fields.append('password')
            existing.save(update_fields=update_fields)
            return Response(
                {'created': False, 'user': UserSerializer(existing).data},
                status=status.HTTP_200_OK,
            )

        if len(password) < 6:
            return Response(
                {'detail': 'Para criar uma nova conta Staff, informe uma senha com pelo menos 6 caracteres.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        final_username = username or email.split('@')[0]
        if User.objects.filter(username__iexact=final_username).exists():
            final_username = f'{final_username}_{uuid.uuid4().hex[:4]}'

        user = User.objects.create_user(
            username=final_username,
            email=email,
            password=password,
            is_staff=True,
        )
        return Response(
            {'created': True, 'user': UserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Groups.objects.all()
    serializer_class = GroupSerializer

    def get_queryset(self):
        if self.request.user and self.request.user.is_authenticated:
            all_groups = str(self.request.query_params.get('all_groups', '')).lower() in ('true', '1', 'yes')
            if self.request.user.is_staff and all_groups:
                return Groups.objects.all().order_by('-created_at')
            return Groups.objects.filter(members__user=self.request.user).distinct()
        return Groups.objects.none()

    def perform_create(self, serializer):
        group = serializer.save()
        user_id = None
        if self.request.user and self.request.user.is_authenticated:
            user_id = str(self.request.user.id)
            UserInGroup.objects.get_or_create(
                group=group,
                user=self.request.user,
                defaults={'role': 'admin', 'is_admin': True},
            )
        publish_event(
            'activity.group_created',
            {
                'group_id': str(group.id),
                'user_id': user_id,
                'entity_type': 'group',
                'entity_id': str(group.id),
                'description': f'Grupo "{group.name}" criado',
            },
        )

    def perform_destroy(self, instance):
        gid = str(instance.id)
        gname = instance.name
        instance.delete()
        publish_event('group.deleted', {'group_id': gid, 'group_name': gname})


class UserInGroupViewSet(viewsets.ModelViewSet):
    queryset = UserInGroup.objects.all()
    serializer_class = UserInGroupSerializer

    def get_queryset(self):
        if not (self.request.user and self.request.user.is_authenticated):
            return UserInGroup.objects.none()
        all_groups = str(self.request.query_params.get('all_groups', '')).lower() in ('true', '1', 'yes')
        if self.request.user.is_staff and (all_groups or self.action in ('retrieve', 'destroy', 'update', 'partial_update')):
            queryset = UserInGroup.objects.select_related('user', 'group').all()
        else:
            queryset = (
                UserInGroup.objects.select_related('user', 'group')
                .filter(group__members__user=self.request.user)
                .distinct()
            )
        group_id = self.request.query_params.get('group') or self.request.query_params.get('group_id')
        user_id = self.request.query_params.get('user') or self.request.query_params.get('user_id')
        if group_id:
            queryset = queryset.filter(group_id=group_id)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        return queryset

    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        group_id = data.get('group') or data.get('group_id')
        user_id = data.get('user') or data.get('user_id')
        if not user_id and request.user and request.user.is_authenticated:
            user_id = request.user.id
        if group_id and 'group' not in data:
            data['group'] = group_id
        if user_id and 'user' not in data:
            data['user'] = user_id

        if 'is_admin' in data and 'role' not in data:
            data['role'] = 'admin' if data['is_admin'] else 'member'
        elif 'role' in data and 'is_admin' not in data:
            data['is_admin'] = data['role'] == 'admin'

        if group_id and user_id:
            existing = UserInGroup.objects.filter(group_id=group_id, user_id=user_id).first()
            if existing:
                if 'role' in data and data['role'] is not None:
                    existing.role = data['role']
                if 'is_admin' in data and data['is_admin'] is not None:
                    existing.is_admin = bool(data['is_admin'])
                existing.save()
                serializer = self.get_serializer(existing)
                return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


UserInGroupSet = UserInGroupViewSet


class GroupInviteViewSet(viewsets.ModelViewSet):
    queryset = GroupInvite.objects.all()
    serializer_class = GroupInviteSerializer

    def get_queryset(self):
        queryset = GroupInvite.objects.all()
        code = self.request.query_params.get('code')
        if self.action == 'list' and not code:
            if self.request.user and self.request.user.is_authenticated:
                queryset = queryset.filter(group__members__user=self.request.user).distinct()
            else:
                return GroupInvite.objects.none()

        group_id = self.request.query_params.get('group') or self.request.query_params.get('group_id')
        active = self.request.query_params.get('active')
        if group_id:
            queryset = queryset.filter(group_id=group_id)
        if code:
            queryset = queryset.filter(code__iexact=code.strip())
        if active is not None and active != '':
            is_active = str(active).lower() in ('true', '1', 'yes')
            queryset = queryset.filter(active=is_active)
        return queryset

    def get_object(self):
        pk = self.kwargs.get(self.lookup_field)
        obj = GroupInvite.objects.filter(code__iexact=str(pk)).first()
        if obj:
            return obj
        return get_object_or_404(GroupInvite, pk=pk)

    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        code = str(data.get('code', '')).strip().upper()
        if not code:
            code = uuid.uuid4().hex[:8].upper()
        data['code'] = code

        if 'group_id' in data and 'group' not in data:
            data['group'] = data['group_id']

        if not data.get('created_by') and request.user and request.user.is_authenticated:
            data['created_by'] = request.user.id

        existing = GroupInvite.objects.filter(code__iexact=code).first()
        if existing:
            if 'group' in data and data['group'] is not None:
                existing.group_id = data['group']
            if 'created_by' in data and data['created_by'] is not None:
                existing.created_by_id = data['created_by']
            if 'active' in data and data['active'] is not None:
                existing.active = bool(data['active'])
            existing.save()
            serializer = self.get_serializer(existing)
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class PriceRecordViewSet(viewsets.ModelViewSet):
    queryset = PriceRecord.objects.all()
    serializer_class = PriceRecordSerializer

    def get_queryset(self):
        if not (self.request.user and self.request.user.is_authenticated):
            return PriceRecord.objects.none()
        queryset = PriceRecord.objects.filter(group__members__user=self.request.user).distinct()
        group_id = self.request.query_params.get('group') or self.request.query_params.get('group_id')
        product_id = self.request.query_params.get('product_id')
        market_id = self.request.query_params.get('market_id')
        if group_id:
            queryset = queryset.filter(group_id=group_id)
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        if market_id:
            queryset = queryset.filter(market_id=market_id)
        return queryset

    def perform_create(self, serializer):
        recorded_by = serializer.validated_data.get('recorded_by')
        if not recorded_by and self.request.user and self.request.user.is_authenticated:
            recorded_by = self.request.user
        record = serializer.save(recorded_by=recorded_by)
        user_id = str(recorded_by.id) if recorded_by else None
        publish_event(
            'price.recorded',
            {
                'record_id': str(record.id),
                'group_id': str(record.group_id),
                'product_id': str(record.product_id),
                'market_id': str(record.market_id),
                'price_cents': record.price_cents,
                'is_promotion': record.is_promotion,
                'recorded_by_id': user_id,
            },
        )
        publish_event(
            'activity.price_recorded',
            {
                'group_id': str(record.group_id),
                'user_id': user_id,
                'entity_type': 'price_record',
                'entity_id': str(record.id),
                'description': f'Preço de R$ {record.price_cents / 100:.2f} registrado',
            },
        )


class ShoppingListViewSet(viewsets.ModelViewSet):
    queryset = ShoppingList.objects.all()
    serializer_class = ShoppingListSerializer

    def get_queryset(self):
        if not (self.request.user and self.request.user.is_authenticated):
            return ShoppingList.objects.none()
        all_groups = str(self.request.query_params.get('all_groups', '')).lower() in ('true', '1', 'yes')
        if self.request.user.is_staff and (all_groups or self.action in ('retrieve', 'destroy', 'update', 'partial_update')):
            queryset = (
                ShoppingList.objects.select_related('owner', 'group')
                .prefetch_related('items', 'group__members__user')
                .all()
            )
        else:
            queryset = (
                ShoppingList.objects.select_related('owner', 'group')
                .prefetch_related('items', 'group__members__user')
                .filter(group__members__user=self.request.user)
                .distinct()
            )
        group_id = self.request.query_params.get('group') or self.request.query_params.get('group_id')
        owner_id = self.request.query_params.get('owner') or self.request.query_params.get('owner_id')
        status_param = self.request.query_params.get('status')
        q = (self.request.query_params.get('q') or '').strip()
        if group_id:
            queryset = queryset.filter(group_id=group_id)
        if owner_id:
            queryset = queryset.filter(owner_id=owner_id)
        if status_param:
            queryset = queryset.filter(status=status_param)
        if q:
            q_clean = q.lstrip('#').strip()
            search_q = (
                Q(name__icontains=q)
                | Q(group__name__icontains=q)
                | Q(owner__username__icontains=q)
                | Q(owner__email__icontains=q)
                | Q(group__members__user__username__icontains=q)
                | Q(group__members__user__email__icontains=q)
            )
            if q_clean.isdigit():
                search_q = search_q | Q(id=int(q_clean))
            queryset = queryset.filter(search_q).distinct()
        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        owner = serializer.validated_data.get('owner')
        if not owner and self.request.user and self.request.user.is_authenticated:
            owner = self.request.user
        shopping_list = serializer.save(owner=owner)
        publish_event(
            'activity.list_created',
            {
                'group_id': str(shopping_list.group_id),
                'user_id': str(owner.id) if owner else None,
                'entity_type': 'shopping_list',
                'entity_id': str(shopping_list.id),
                'description': f'Lista "{shopping_list.name}" criada',
            },
        )


class ShoppingListItemViewSet(viewsets.ModelViewSet):
    queryset = ShoppingListItem.objects.all()
    serializer_class = ShoppingListItemSerializer

    def get_queryset(self):
        if not (self.request.user and self.request.user.is_authenticated):
            return ShoppingListItem.objects.none()
        all_groups = str(self.request.query_params.get('all_groups', '')).lower() in ('true', '1', 'yes')
        if self.request.user.is_staff and (all_groups or self.action in ('retrieve', 'destroy', 'update', 'partial_update')):
            queryset = ShoppingListItem.objects.all()
        else:
            queryset = ShoppingListItem.objects.filter(
                shopping_list__group__members__user=self.request.user
            ).distinct()
        shopping_list_id = (
            self.request.query_params.get('shopping_list')
            or self.request.query_params.get('shopping_list_id')
        )
        product_id = self.request.query_params.get('product_id')
        checked = self.request.query_params.get('checked')
        if shopping_list_id:
            queryset = queryset.filter(shopping_list_id=shopping_list_id)
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        if checked is not None and checked != '':
            is_checked = str(checked).lower() in ('true', '1', 'yes')
            queryset = queryset.filter(checked=is_checked)
        return queryset

    def perform_create(self, serializer):
        added_by = serializer.validated_data.get('added_by')
        if not added_by and self.request.user and self.request.user.is_authenticated:
            added_by = str(self.request.user.id)
        item = serializer.save(added_by=added_by)
        user_id = (
            str(self.request.user.id)
            if self.request.user and self.request.user.is_authenticated
            else added_by
        )
        publish_event(
            'activity.item_added',
            {
                'group_id': str(item.shopping_list.group_id),
                'user_id': user_id,
                'entity_type': 'shopping_list_item',
                'entity_id': str(item.id),
                'description': f'Item "{item.product_name}" adicionado à lista',
            },
        )

    def perform_update(self, serializer):
        old_checked = serializer.instance.checked
        item = serializer.save()
        if item.checked != old_checked:
            user_id = (
                str(self.request.user.id)
                if self.request.user and self.request.user.is_authenticated
                else None
            )
            status_label = 'comprado' if item.checked else 'pendente'
            publish_event(
                'activity.item_checked',
                {
                    'group_id': str(item.shopping_list.group_id),
                    'user_id': user_id,
                    'entity_type': 'shopping_list_item',
                    'entity_id': str(item.id),
                    'description': f'Item "{item.product_name}" marcado como {status_label}',
                },
            )


class CommunityOfferViewSet(viewsets.ModelViewSet):
    queryset = CommunityOffer.objects.all()
    serializer_class = CommunityOfferSerializer
    permission_classes = [IsAuthenticated]

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

        if radius_raw in ('all', 'none', '0', 'sem_limite'):
            radius_km = None
        elif radius_raw:
            try:
                val = float(radius_raw.replace(',', '.'))
                if 1 <= val <= 500:
                    radius_km = val
            except ValueError:
                radius_km = None
        elif lat is not None and lng is not None:
            pref = getattr(self.request.user, 'preferred_radius_km', 30)
            radius_km = float(pref) if pref else None

        return lat, lng, radius_km

    def get_queryset(self):
        queryset = CommunityOffer.objects.select_related('reported_by').all()
        active_only = self.request.query_params.get('active_only', 'true').lower() in ('true', '1', 'yes')
        mod_param = (self.request.query_params.get('moderation_status') or '').strip().lower()

        if self.request.user.is_staff and mod_param:
            if mod_param != 'all':
                queryset = queryset.filter(moderation_status=mod_param)
        else:
            queryset = queryset.filter(moderation_status='approved')
            if active_only:
                queryset = queryset.filter(is_active=True)

        scope = (self.request.query_params.get('scope') or '').strip().lower()
        group_id = self.request.query_params.get('group') or self.request.query_params.get('group_id')
        market_id = (self.request.query_params.get('market_id') or '').strip()
        category = (self.request.query_params.get('category') or '').strip()
        city = (self.request.query_params.get('city') or '').strip()
        ean = (self.request.query_params.get('ean') or '').strip()
        q = (self.request.query_params.get('q') or '').strip()

        if scope == 'group' and group_id:
            queryset = queryset.filter(
                group_id=group_id,
                group__members__user=self.request.user,
            ).distinct()
        elif group_id and scope != 'community':
            queryset = queryset.filter(
                group_id=group_id,
                group__members__user=self.request.user,
            ).distinct()

        if market_id:
            queryset = queryset.filter(market_id=market_id)
        if category:
            queryset = queryset.filter(category__iexact=category)
        if city:
            queryset = queryset.filter(city__icontains=city)
        if ean:
            queryset = queryset.filter(ean=ean)
        if q:
            queryset = queryset.filter(
                Q(product_name__icontains=q)
                | Q(brand__icontains=q)
                | Q(market_name__icontains=q)
                | Q(city__icontains=q)
                | Q(ean__icontains=q)
            )

        lat, lng, radius_km = self._parse_geo_params()
        strict_geo = self.request.query_params.get('strict_geo', 'false').lower() in ('true', '1', 'yes')
        if lat is not None and lng is not None and radius_km is not None:
            min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, radius_km)
            geo_q = Q(
                latitude__gte=min_lat,
                latitude__lte=max_lat,
                longitude__gte=min_lng,
                longitude__lte=max_lng,
            )
            if not strict_geo:
                geo_q = geo_q | Q(latitude__isnull=True) | Q(longitude__isnull=True)
            queryset = queryset.filter(geo_q)

        return queryset.annotate(
            _trust_score=F('confirmations_count') - F('reports_count')
        ).order_by('-_trust_score', '-confirmations_count', '-created_at')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        lat, lng, radius_km = self._parse_geo_params()
        strict_geo = request.query_params.get('strict_geo', 'false').lower() in ('true', '1', 'yes')

        offers = list(queryset)
        if lat is not None and lng is not None:
            filtered = []
            for offer in offers:
                if offer.latitude is not None and offer.longitude is not None:
                    dist = haversine_km(lat, lng, offer.latitude, offer.longitude)
                    offer._distance_km = dist
                    if radius_km is None or dist <= radius_km:
                        filtered.append(offer)
                elif not strict_geo:
                    offer._distance_km = None
                    filtered.append(offer)
            offers = filtered

        serializer = self.get_serializer(offers, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        user = self.request.user
        group = serializer.validated_data.get('group')

        if user.community_banned and group is None:
            raise PermissionDenied(
                'Sua conta está restrita para publicações na comunidade global.'
            )

        if not user.is_staff:
            since = timezone.now() - timedelta(hours=24)
            recent_count = CommunityOffer.objects.filter(
                reported_by=user,
                created_at__gte=since,
            ).count()
            if recent_count >= DAILY_OFFER_LIMIT:
                raise ValidationError(
                    {'detail': f'Limite diário de {DAILY_OFFER_LIMIT} ofertas atingido.'}
                )

        offer = serializer.save(reported_by=user)
        OfferVote.objects.get_or_create(
            offer=offer,
            user=user,
            defaults={'vote_type': 'confirm'},
        )
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
                'reported_by_id': user.id,
                'broadcast_alert': bool(user.is_staff and self.request.data.get('broadcast_alert')),
            },
        )

    @action(detail=True, methods=['post'], url_path='vote')
    def vote(self, request, pk=None):
        offer = self.get_object()
        vote_type = (request.data.get('vote_type') or '').strip().lower()
        if vote_type not in ('confirm', 'expired', 'abuse'):
            return Response(
                {'detail': 'vote_type must be "confirm", "expired", or "abuse".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing_vote = OfferVote.objects.filter(offer=offer, user=request.user).first()
        if existing_vote and existing_vote.vote_type == vote_type and vote_type != 'abuse':
            existing_vote.delete()
        else:
            OfferVote.objects.update_or_create(
                offer=offer,
                user=request.user,
                defaults={'vote_type': vote_type},
            )

        confirmations_count = OfferVote.objects.filter(offer=offer, vote_type='confirm').count()
        reports_count = OfferVote.objects.filter(offer=offer, vote_type='expired').count()
        abuse_reports_count = OfferVote.objects.filter(offer=offer, vote_type='abuse').count()
        offer.confirmations_count = confirmations_count
        offer.reports_count = reports_count
        offer.abuse_reports_count = abuse_reports_count

        update_fields = ['confirmations_count', 'reports_count', 'abuse_reports_count', 'updated_at']
        trust_score = confirmations_count - reports_count

        if vote_type == 'abuse' and (abuse_reports_count >= 2 or request.user.is_staff):
            offer.is_active = False
            offer.moderation_status = 'flagged'
            update_fields.extend(['is_active', 'moderation_status'])
        elif (reports_count >= 3 and reports_count > confirmations_count) or trust_score <= -2:
            offer.is_active = False
            update_fields.append('is_active')

        offer.save(update_fields=update_fields)

        if vote_type == 'abuse':
            publish_event(
                'offer.flagged',
                {
                    'offer_id': offer.id,
                    'user_id': request.user.id,
                    'is_staff': request.user.is_staff,
                    'abuse_reports_count': abuse_reports_count,
                },
            )
        else:
            publish_event(
                'offer.voted',
                {
                    'offer_id': offer.id,
                    'user_id': request.user.id,
                    'vote_type': vote_type,
                    'confirmations_count': confirmations_count,
                    'reports_count': reports_count,
                },
            )
        return Response(self.get_serializer(offer).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='moderate')
    def moderate(self, request, pk=None):
        if not request.user.is_staff:
            raise PermissionDenied('Apenas moderadores podem executar esta ação.')

        offer = get_object_or_404(CommunityOffer, pk=pk)
        mod_action = (request.data.get('action') or '').strip().lower()
        if mod_action == 'approve':
            offer.moderation_status = 'approved'
            offer.is_active = True
            offer.save(update_fields=['moderation_status', 'is_active', 'updated_at'])
        elif mod_action == 'remove':
            offer.moderation_status = 'removed'
            offer.is_active = False
            offer.save(update_fields=['moderation_status', 'is_active', 'updated_at'])
        elif mod_action == 'ban_author':
            offer.moderation_status = 'removed'
            offer.is_active = False
            offer.save(update_fields=['moderation_status', 'is_active', 'updated_at'])
            if offer.reported_by:
                offer.reported_by.community_banned = True
                offer.reported_by.save(update_fields=['community_banned', 'updated_at'])
        else:
            return Response(
                {'detail': 'action deve ser "approve", "remove" ou "ban_author".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(self.get_serializer(offer).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        offers_shared = CommunityOffer.objects.filter(reported_by=request.user).count()
        confirmations_given = OfferVote.objects.filter(user=request.user, vote_type='confirm').count()
        alerts_triggered = PriceAlert.objects.filter(offer__reported_by=request.user).count()
        total = offers_shared + confirmations_given
        if total >= 10:
            level = 'Guardião do Preço'
        elif total >= 3:
            level = 'Caçador de Ofertas'
        else:
            level = 'Explorador'
        return Response(
            {
                'offers_shared': offers_shared,
                'confirmations_given': confirmations_given,
                'alerts_triggered': alerts_triggered,
                'level': level,
            },
            status=status.HTTP_200_OK,
        )


class PriceAlertViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PriceAlert.objects.all()
    serializer_class = PriceAlertSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = PriceAlert.objects.filter(
            Q(user=self.request.user) | Q(group__members__user=self.request.user)
        ).distinct()
        group_id = self.request.query_params.get('group') or self.request.query_params.get('group_id')
        unread_only = self.request.query_params.get('unread_only', '').lower() in ('true', '1', 'yes')
        if group_id:
            queryset = queryset.filter(
                Q(group_id=group_id) | Q(user=self.request.user, group__isnull=True)
            )
        if unread_only:
            queryset = queryset.filter(is_read=False)
        return queryset.order_by('-created_at')

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        alert = self.get_object()
        alert.is_read = True
        alert.save(update_fields=['is_read'])
        return Response(self.get_serializer(alert).data, status=status.HTTP_200_OK)


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ActivityLog.objects.all()
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ActivityLog.objects.filter(group__members__user=self.request.user).distinct()
        group_id = self.request.query_params.get('group') or self.request.query_params.get('group_id')
        if group_id:
            queryset = queryset.filter(group_id=group_id)
        return queryset.order_by('-created_at')


class RegisterUserView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if not data.get('username') and data.get('display_name'):
            data['username'] = data['display_name']
        if not data.get('password2') and data.get('password'):
            data['password2'] = data['password']

        serializer = RegisterSerializer(data=data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            refresh['is_staff'] = user.is_staff
            return Response(
                {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                    'user': UserSerializer(user).data,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FlexibleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        identifier = (
            request.data.get('email')
            or request.data.get('username')
            or ''
        ).strip()
        password = request.data.get('password') or ''

        if not identifier or not password:
            return Response(
                {'detail': 'Credentials required.', 'error': 'invalid-credentials'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(email__iexact=identifier).first()
        if not user:
            user = User.objects.filter(username__iexact=identifier).first()

        if not user:
            return Response(
                {'detail': 'User not found.', 'error': 'user-not-found'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.check_password(password):
            return Response(
                {'detail': 'Invalid password.', 'error': 'wrong-password'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        refresh['is_staff'] = user.is_staff
        return Response(
            {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response(
                {'detail': 'Email is required.', 'error': 'invalid-email'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        staff_only = bool(request.data.get('staff_only', False))
        username = (
            request.data.get('username')
            or request.data.get('display_name')
            or email.split('@')[0]
        ).strip()
        photo_url = request.data.get('photo_url')

        user = User.objects.filter(email__iexact=email).first()
        if staff_only:
            if not user or not user.is_staff:
                return Response(
                    {
                        'detail': 'Acesso restrito: apenas contas com permissão de Staff podem acessar o painel web.',
                        'error': 'staff-required',
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            if photo_url and user.photo_url != photo_url:
                user.photo_url = photo_url
                user.save(update_fields=['photo_url', 'updated_at'])
        elif not user:
            if User.objects.filter(username__iexact=username).exists():
                username = f'{username}_{uuid.uuid4().hex[:6]}'
            user = User.objects.create_user(
                username=username,
                email=email,
                password=uuid.uuid4().hex,
                photo_url=photo_url,
            )
        else:
            if photo_url and user.photo_url != photo_url:
                user.photo_url = photo_url
                user.save(update_fields=['photo_url', 'updated_at'])

        refresh = RefreshToken.for_user(user)
        refresh['is_staff'] = user.is_staff
        return Response(
            {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


def health_check(request):
    return HttpResponse('OK', status=200)
