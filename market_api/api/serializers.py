from rest_framework import serializers
from .models import Market


class MarketSerializer(serializers.ModelSerializer):
    linked_groups_count = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()
    is_my_group = serializers.SerializerMethodField()

    class Meta:
        model = Market
        fields = [
            'id',
            'group_id',
            'name',
            'brand',
            'address',
            'city',
            'latitude',
            'longitude',
            'osm_place_id',
            'is_verified',
            'linked_group_ids',
            'linked_groups_count',
            'distance_km',
            'is_my_group',
            'status',
            'added_by',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at', 'linked_groups_count', 'distance_km', 'is_my_group']
        extra_kwargs = {
            'added_by': {'required': False, 'allow_blank': True},
            'group_id': {'required': False, 'allow_blank': True},
            'brand': {'required': False, 'allow_blank': True},
            'address': {'required': False, 'allow_blank': True},
            'city': {'required': False, 'allow_blank': True},
            'osm_place_id': {'required': False, 'allow_blank': True},
            'linked_group_ids': {'required': False},
        }

    def get_linked_groups_count(self, obj) -> int:
        ids = set(str(g) for g in (obj.linked_group_ids or []) if str(g).strip())
        if obj.group_id and str(obj.group_id).strip().lower() != 'global':
            ids.add(str(obj.group_id).strip())
        return len(ids)

    def get_distance_km(self, obj):
        dist = getattr(obj, '_distance_km', None)
        return round(dist, 2) if dist is not None else None

    def get_is_my_group(self, obj) -> bool:
        request = self.context.get('request')
        if not request:
            return False
        gid = (request.query_params.get('group_id') or request.query_params.get('group') or '').strip()
        if not gid:
            return False
        if str(obj.group_id) == gid:
            return True
        return gid in [str(g) for g in (obj.linked_group_ids or [])]
