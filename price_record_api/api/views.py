from django.shortcuts import render
from rest_framework import viewsets
from .models import PriceRecord
from .serializers import PriceRecordSerializer
from django.http import HttpResponse

class PriceRecordViewSet(viewsets.ModelViewSet):
    queryset = PriceRecord.objects.all()
    serializer_class = PriceRecordSerializer

def health_check(request):
    return HttpResponse("OK", status=200)


