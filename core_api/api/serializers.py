import uuid
from rest_framework import serializers
from .moderation import (
    contains_inappropriate_content,
    is_valid_ean,
    validate_price_cents,
)
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


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'username',
            'photo_url',
            'photo_public_id',
            'biometric_enabled',
            'last_active_group',
            'preferred_radius_km',
            'community_banned',
            'is_staff',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'community_banned', 'is_staff', 'created_at', 'updated_at']

    def validate_preferred_radius_km(self, value):
        if value is not None and (value < 1 or value > 500):
            raise serializers.ValidationError('O raio deve estar entre 1 e 500 km.')
        return value


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Groups
        fields = '__all__'
        read_only_fields = ['id', 'createdAt']


class UserInGroupSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_photo_url = serializers.URLField(source='user.photo_url', read_only=True, allow_null=True)

    class Meta:
        model = UserInGroup
        fields = [
            'id',
            'group',
            'user',
            'role',
            'is_admin',
            'joined_at',
            'user_username',
            'user_email',
            'user_photo_url',
        ]
        read_only_fields = ['id', 'joined_at', 'user_username', 'user_email', 'user_photo_url']


class GroupInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupInvite
        fields = '__all__'
        read_only_fields = ['created_at']
        extra_kwargs = {
            'created_by': {'required': False, 'allow_null': True},
        }


class PriceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceRecord
        fields = '__all__'
        read_only_fields = ('id', 'recorded_at')
        extra_kwargs = {
            'recorded_by': {'required': False, 'allow_null': True},
        }


class ShoppingListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShoppingList
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'owner': {'required': False, 'allow_null': True},
        }


class ShoppingListItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShoppingListItem
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'added_by': {'required': False, 'allow_null': True, 'allow_blank': True},
        }


class RegisterSerializer(serializers.ModelSerializer):
    username = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=True)
    password2 = serializers.CharField(write_only=True, required=False, allow_blank=True)
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'photo_url', 'password', 'password2']

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('Email already in use.')
        return email

    def validate(self, attrs):
        password = attrs.get('password', '')
        password2 = attrs.get('password2') or password
        if password != password2:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        attrs['password2'] = password2

        email = attrs.get('email', '').strip().lower()
        username = (attrs.get('username') or '').strip()
        if not username:
            username = email.split('@')[0] if '@' in email else f'user_{uuid.uuid4().hex[:6]}'

        if User.objects.filter(username__iexact=username).exists():
            username = f'{username}_{uuid.uuid4().hex[:6]}'
        attrs['username'] = username
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2', None)
        return User.objects.create_user(**validated_data)


class CommunityOfferSerializer(serializers.ModelSerializer):
    my_vote = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()
    reported_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CommunityOffer
        fields = [
            'id',
            'ean',
            'product_name',
            'brand',
            'category',
            'market_name',
            'city',
            'latitude',
            'longitude',
            'price_cents',
            'reference_avg_cents',
            'discount_percent',
            'is_promotion',
            'confirmations_count',
            'reports_count',
            'abuse_reports_count',
            'moderation_status',
            'is_active',
            'group',
            'my_vote',
            'is_mine',
            'distance_km',
            'reported_by_name',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'reference_avg_cents',
            'discount_percent',
            'confirmations_count',
            'reports_count',
            'abuse_reports_count',
            'moderation_status',
            'is_active',
            'my_vote',
            'is_mine',
            'distance_km',
            'reported_by_name',
            'created_at',
        ]

    def validate(self, attrs):
        for field in ('product_name', 'brand', 'market_name', 'city'):
            val = attrs.get(field)
            if val and contains_inappropriate_content(val):
                raise serializers.ValidationError(
                    {field: 'Conteúdo impróprio detectado. Revise o texto informado.'}
                )

        price_cents = attrs.get('price_cents')
        if price_cents is not None:
            ok, err = validate_price_cents(price_cents)
            if not ok:
                raise serializers.ValidationError({'price_cents': err})

        ean = (attrs.get('ean') or '').strip()
        if ean and not is_valid_ean(ean):
            raise serializers.ValidationError(
                {'ean': 'Código de barras EAN inválido (use 8, 12, 13 ou 14 dígitos válidos).'}
            )
        return attrs

    def get_my_vote(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None
        return (
            OfferVote.objects.filter(offer=obj, user=user)
            .values_list('vote_type', flat=True)
            .first()
        )

    def get_is_mine(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        return obj.reported_by_id == user.id

    def get_distance_km(self, obj):
        dist = getattr(obj, '_distance_km', None)
        return round(dist, 1) if dist is not None else None

    def get_reported_by_name(self, obj):
        if not obj.reported_by:
            return 'Comunidade'
        return obj.reported_by.first_name or obj.reported_by.username


class PriceAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceAlert
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLog
        fields = '__all__'
        read_only_fields = ['id', 'created_at']

