from rest_framework import serializers
from .models import *
from django.contrib.auth.password_validation import validate_password


class UserSerializer (serializers.ModelSerializer):
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
            'last_active_group_updated_at',
            'created_at',
            'updated_at',
            'is_active',
        ]
        read_only_fields = ['username', 'last_active_group', 'last_active_group_updated_at', 'created_at', 'updated_at']

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

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'photo_url', 'password', 'password2']

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('Username already taken.')
        return value
    
    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Email already in use.')
        return value.lower()

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        return User.objects.create_user(**validated_data)

