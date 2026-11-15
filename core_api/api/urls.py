from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'groups', GroupViewSet)
router.register(r'user-groups', UserInGroupSet)
router.register(r'price-records', PriceRecordViewSet)
router.register(r'group-invites', GroupInviteViewSet)
router.register(r'shopping-lists', ShoppingListViewSet)
router.register(r'shopping-list-items', ShoppingListItemViewSet)

urlpatterns = [
    path('', include(router.urls)),
]

    