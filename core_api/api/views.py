from django.shortcuts import render
from .models import *
from .serializers import *
from rest_framework import viewsets
from django.http import HttpResponse

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

class GroupViewSet(viewsets.ModelViewSet):
    queryset = Groups.objects.all()
    serializer_class = GroupSerializer

class UserInGroupSet(viewsets.ModelViewSet):
    queryset = UserInGroup.objects.all()
    serializer_class = UserInGroupSerializer
    
class GroupInviteViewSet(viewsets.ModelViewSet):
    queryset = GroupInvite.objects.all()
    serializer_class = GroupInviteSerializer

class PriceRecordViewSet(viewsets.ModelViewSet):
    queryset = PriceRecord.objects.all()
    serializer_class = PriceRecordSerializer
    
class ShoppingListViewSet(viewsets.ModelViewSet):
    queryset = ShoppingList.objects.all()
    serializer_class = ShoppingListSerializer

class ShoppingListItemViewSet(viewsets.ModelViewSet):
    queryset = ShoppingListItem.objects.all()
    serializer_class = ShoppingListItemSerializer
    
def health_check(request):
    return HttpResponse("OK", status=200)