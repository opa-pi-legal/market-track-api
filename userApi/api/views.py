from django.shortcuts import render
from .models import User
from .serializers import UserSerializer
from rest_framework import viewsets
from django.http import HttpResponse
# Create your views here.

class UserViewSet(viewsets.ModelViewSet):
    print("teste")
    queryset = User.objects.all()
    serializer_class = UserSerializer


def health_check(request):
    return HttpResponse("OK", status=200)

