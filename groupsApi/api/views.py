from django.shortcuts import render
from rest_framework import viewsets
from .models import Groups
from .serializers import GroupSerializer

class GroupViewSet(viewsets.ModelViewSet):
    queryset = Groups.objects.all()
    serializer_class = GroupSerializer
