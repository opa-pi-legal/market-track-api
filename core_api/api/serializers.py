from rest_framework import serializers
from .models import *

class UserSerializer (serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'
        
        read_only_fields = "created_at", "updated_at"

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Groups
        fields = '__all__'

class UserInGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserInGroup
        fields = "__all__"
        
class GroupInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupInvite
        fields = '__all__'
        read_only_fields = ['created_at']
        
class PriceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceRecord
        fields = '__all__'
        
        read_only_fields = ('recorded_at', 'recorded_by') 
        
class ShoppingListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShoppingList
        fields = '__all__'
        
        read_only_fields = ['created_at', 'updated_at']
        
class ShoppingListItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShoppingListItem
        fields = '__all__'
        
        read_only_fields = ['created_at', 'updated_at']