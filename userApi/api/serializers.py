from rest_framework import serializers
from .models import User, UserInGroup

class UserSerializer (serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", 
            "display_name", 
            "email", 
            "photo_url", 
            "photo_public_id", 
            "biometric_enabled", 
            "last_active_group_id", 
            "last_active_group_updated_at", 
            "created_at", 
            "updated_at"
        ]
        
        read_only_fields = ["created_at", "updated_at"]
        
class UserInGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserInGroup
        fields = ["userId","GroupId"]