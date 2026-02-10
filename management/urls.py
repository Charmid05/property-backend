from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OfficeViewSet

router = DefaultRouter()
router.register(r'offices', OfficeViewSet, basename='office')

# URL patterns
urlpatterns = [
    # Include the router URLs
    path('management/', include(router.urls)),
]
