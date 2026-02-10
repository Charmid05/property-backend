
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TenantViewSet, TenantDocumentViewSet

# Create router for viewsets
router = DefaultRouter()
router.register(r'tenants', TenantViewSet, basename='tenant')
router.register(r'tenant-documents', TenantDocumentViewSet,
                basename='tenant-document')

app_name = 'tenants'

urlpatterns = [
    path('', include(router.urls)),
]
