from rest_framework import serializers
from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = ['id', 'is_global', 'verified_source', 'created_at', 'last_updated']
        extra_kwargs = {
            'added_by': {'required': False, 'allow_blank': True},
        }
