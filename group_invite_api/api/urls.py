from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import GroupInviteViewSet

router = DefaultRouter()
router.register(r'group-invites', GroupInviteViewSet)

urlpatterns = [
    path('', include(router.urls)),
]