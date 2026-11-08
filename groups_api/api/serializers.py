from rest_framework import serializers
from .models import Groups, UserInGroup, GroupInvite

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Groups
        fields = [
            'name', 'adminId', 'inviteCode', 'description', 'color', 'photoUrl', 'suggestedCatalogEnabled',
        ]

class UserInGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserInGroup
        fields = ["user_id","group"]
        
class GroupInviteSerialize(serializers.ModelSerializer):
    class Meta:
        model = GroupInvite
        fields = ["code", "group","created_by", "active", "created_at"]
        
        read_only_fields = ["created_at"]