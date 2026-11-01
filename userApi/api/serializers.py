from rest_framework import serializers
from .models import User

class UserSerializer (serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "displayName", "email","photoUrl","photoPublicId","biometricEnabled","lastActiveGroupId", "lastActiveGroupUpdatedAt","createdAt","updatedAt"]
