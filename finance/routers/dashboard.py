from rest_framework.routers import DefaultRouter
from finance.views import DashboardViewSet

router = DefaultRouter()
router.register(r'dashboard', DashboardViewSet, basename='dashboard')
