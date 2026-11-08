from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import GroupViewSet, UserInGroupSet, GroupInviteSet

router = DefaultRouter()
router.register(r'groups', GroupViewSet)
router.register(r'users-groups', UserInGroupSet)
router.register(r'group-invites', GroupInviteSet)

urlpatterns = [
    path('', include(router.urls)),
]