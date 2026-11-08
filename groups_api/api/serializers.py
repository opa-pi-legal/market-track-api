from rest_framework import serializers
from .models import Groups, UserInGroup

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Groups
        fields = [
            'name', 'adminId', 'inviteCode', 'description', 'color', 'photoUrl', 'suggestedCatalogEnabled',
        ]

class UserInGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserInGroup
        fields = ["user_id","group","is_admin","joined_at"]
