from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'properties'

router = DefaultRouter()
router.register(r'units', views.UnitViewSet, basename='units')

urlpatterns = [
    # Core property views
    path('properties/', views.PropertyListCreateView.as_view(),
         name='property-list-create'),
    path('properties/<int:id>/',
         views.PropertyRetrieveUpdateDestroyView.as_view(), name='property-detail'),

    # Assign manager API
    path('properties/assign-manager/',
         views.AssignPropertyManagerView.as_view(),
         name='assign-property-manager'),

    # ViewSet-based routes
    path('', include(router.urls)),
]
