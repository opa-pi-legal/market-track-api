from rest_framework import serializers
from .models import Market

class MarketSerializer (serializers.ModelSerializer):
    class Meta:
        model = Market
        fields = [
            'group_id',
            'name',
            'brand',
            'address',
            'status',
            'added_by',  
            'created_at',
        ]
    
        read_only_fields = ['created_at']