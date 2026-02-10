from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MaintenanceRequestViewSet

# Create router for viewsets
router = DefaultRouter()
router.register(r'requests', MaintenanceRequestViewSet, basename='maintenance-request')

app_name = 'maintenance'

urlpatterns = [
    path('maintenance/', include(router.urls)),
]

