from django.shortcuts import render
from .models import Product
from .serializers import ProductSerializer
from rest_framework import viewsets
from django.http import HttpResponse

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

def health_check(request):
    return HttpResponse("OK", status=200)
