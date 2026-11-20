from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    ActivityLogViewSet,
    CommunityOfferViewSet,
    FlexibleLoginView,
    GoogleLoginView,
    GroupInviteViewSet,
    GroupViewSet,
    PriceAlertViewSet,
    PriceRecordViewSet,
    RegisterUserView,
    ShoppingListItemViewSet,
    ShoppingListViewSet,
    UserInGroupViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'groups', GroupViewSet)
router.register(r'user-groups', UserInGroupViewSet)
router.register(r'users-groups', UserInGroupViewSet, basename='users-groups')
router.register(r'price-records', PriceRecordViewSet)
router.register(r'group-invites', GroupInviteViewSet)
router.register(r'shopping-lists', ShoppingListViewSet)
router.register(r'shopping-list-items', ShoppingListItemViewSet)
router.register(r'community-offers', CommunityOfferViewSet)
router.register(r'price-alerts', PriceAlertViewSet)
router.register(r'activity-logs', ActivityLogViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('login/', FlexibleLoginView.as_view(), name='token_obtain_pair'),
    path('google-login/', GoogleLoginView.as_view(), name='google_login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('register/', RegisterUserView.as_view(), name='register-user'),
]
