from rest_framework import serializers
from .models import GroupInvite

class GroupInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupInvite
        fields = ['code', 'group_id', 'created_by', 'active', 'created_at']
        read_only_fields = ['created_at']