from rest_framework import serializers
from .models import Groups

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Groups
        fields = [
            'name', 'adminId', 'inviteCode', 'description', 'color', 'photoUrl', 'suggestedCatalogEnabled',
        ]