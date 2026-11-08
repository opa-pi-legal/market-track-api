from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PriceRecordViewSet

router = DefaultRouter()
router.register(r'price-records', PriceRecordViewSet)

urlpatterns = [
    path('', include(router.urls)),
]