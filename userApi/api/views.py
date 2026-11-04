from django.shortcuts import render
from .models import User, UserInGroup
from .serializers import UserSerializer, UserInGroupSerializer
from rest_framework import viewsets
from django.http import HttpResponse
from .utils import publicar_evento_entrar_grupo
# Create your views here.

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

class UserInGroupSet(viewsets.ModelViewSet):
     queryset = UserInGroup.objects.all()
     serializer_class = UserInGroupSerializer
     
     def perform_create(self, serializer):
        user_group = serializer.save()
        print(user_group.user_id)
        dados = {
            "user_id": user_group.user_id.id,
            "group_id": user_group.group_id
        }
        
        publicar_evento_entrar_grupo(dados)
        

def health_check(request):
    return HttpResponse("OK", status=200)

