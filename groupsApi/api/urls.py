from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import GroupViewSet, UserInGroupSet

router = DefaultRouter()
router.register(r'groups', GroupViewSet)
router.register(r"users-groups", UserInGroupSet)

urlpatterns = [
    path('', include(router.urls)),
]