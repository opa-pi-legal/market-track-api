from django.shortcuts import render
from .models import Market
from .serializers import MarketSerializer
from rest_framework import viewsets
from django.http import HttpResponse

class MarketViewSet(viewsets.ModelViewSet):
    queryset = Market.objects.all()
    serializer_class = MarketSerializer
    
def health_check(request):
    return HttpResponse("OK", status=200)

