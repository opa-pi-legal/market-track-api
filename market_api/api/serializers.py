from rest_framework import serializers
from .models import Market


class MarketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Market
        fields = [
            'id',
            'group_id',
            'name',
            'brand',
            'address',
            'status',
            'added_by',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {
            'added_by': {'required': False, 'allow_blank': True},
            'brand': {'required': False, 'allow_blank': True},
            'address': {'required': False, 'allow_blank': True},
        }
