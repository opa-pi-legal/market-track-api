from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, health_check, UserInGroupSet

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'users-groups', UserInGroupSet)

urlpatterns = [
    path('', include(router.urls)),
]
