from rest_framework.routers import DefaultRouter
from finance.views import UserAccountViewSet

router = DefaultRouter()
router.register(r'accounts', UserAccountViewSet, basename='account')
