from django.shortcuts import render
from rest_framework import viewsets
from .models import Groups, UserInGroup
from .serializers import GroupSerializer, UserInGroupSerializer
from django.http import HttpResponse

class GroupViewSet(viewsets.ModelViewSet):
    queryset = Groups.objects.all()
    serializer_class = GroupSerializer

class UserInGroupSet(viewsets.ModelViewSet):
    queryset = UserInGroup.objects.all()
    serializer_class = UserInGroupSerializer

def health_check(self):
    return HttpResponse("OK", status=200)