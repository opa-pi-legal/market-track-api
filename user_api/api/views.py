from django.shortcuts import render
from .models import User
from .serializers import UserSerializer
from rest_framework import viewsets
from django.http import HttpResponse

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

def health_check(request):
    return HttpResponse("OK", status=200)