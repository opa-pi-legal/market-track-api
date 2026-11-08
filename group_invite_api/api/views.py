from http.client import HTTPResponse

from django.shortcuts import render
from rest_framework import viewsets
from .models import GroupInvite
from .serializers import GroupInviteSerializer
from django.http import HttpResponse

class GroupInviteViewSet(viewsets.ModelViewSet):
    queryset = GroupInvite.objects.all()
    serializer_class = GroupInviteSerializer
    
def health_check(request):
    return HttpResponse("OK", status=200)


