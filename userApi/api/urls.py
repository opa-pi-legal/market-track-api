from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, health_check

router = DefaultRouter()
router.register(r'users', UserViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
