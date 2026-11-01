from django.shortcuts import render
from rest_framework import viewsets
from .models import Groups
from .serializers import GroupSerializer
from django.http import HttpResponse

class GroupViewSet(viewsets.ModelViewSet):
    queryset = Groups.objects.all()
    serializer_class = GroupSerializer

def health_check(self):
    return HttpResponse("OK", status=200)