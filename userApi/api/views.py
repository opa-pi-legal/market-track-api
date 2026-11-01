from django.shortcuts import render
from .models import User, UserInGroup
from .serializers import UserSerializer, UserInGroupSerializer
from rest_framework import viewsets
from django.http import HttpResponse
# Create your views here.

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

class UserInGroupSet(viewsets.ModelViewSet):
     queryset = UserInGroup.objects.all()
     serializer_class = UserInGroupSerializer

def health_check(request):
    return HttpResponse("OK", status=200)

