from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ShoppingListItemViewSet, ShoppingListViewSet

router = DefaultRouter()
router.register(r'shopping-lists', ShoppingListViewSet )
router.register(r'shopping-list-items', ShoppingListItemViewSet )

urlpatterns = [
    path('', include(router.urls)),
]