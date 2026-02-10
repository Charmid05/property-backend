from rest_framework import viewsets, status
from .serializers import UnitListSerializer, UnitDetailSerializer, UnitCreateUpdateSerializer
from .models import Unit
from rest_framework import filters
from .serializers import (
    PropertyListSerializer,
    PropertyDetailSerializer,
    PropertyCreateUpdateSerializer,
    AssignPropertyManagerSerializer
)
from .models import Property
from tenant.models import Tenant
from rest_framework import generics, status, filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from .models import Unit
from rest_framework.views import APIView
from django.db import transaction
from django.db.models import Count, Q


class PropertyPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class PropertyListCreateView(generics.ListCreateAPIView):
    queryset = Property.objects.select_related('manager', 'office').all()
    permission_classes = [IsAuthenticated]
    pagination_class = PropertyPagination
    filter_backends = [DjangoFilterBackend,
                       filters.SearchFilter, filters.OrderingFilter]

    filterset_fields = {
        'is_active': ['exact'],
        'created_at': ['gte', 'lte', 'exact', 'year', 'month'],
    }

    search_fields = ['name', 'address', 'description']
    ordering_fields = ['name', 'created_at', 'updated_at']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return PropertyCreateUpdateSerializer
        return PropertyListSerializer

    def perform_create(self, serializer):
        serializer.save()

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .annotate(
                # ✅ use 'units' here
                total_units=Count("units", distinct=True),
                occupied_units_count=Count(
                    "units",
                    filter=Q(units__occupied_status=Unit.OccupiedStatus.OCCUPIED),
                    distinct=True,
                ),
            )
        )

        user = self.request.user
        if user.role == 'property_manager':
            queryset = queryset.filter(manager=user)

        return queryset


class PropertyRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Property.objects.select_related('manager', 'office').all()
    serializer_class = PropertyDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return PropertyCreateUpdateSerializer
        return PropertyDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if self.request.method == 'DELETE' and user.role != 'admin':
            return queryset.none()
        if user.role == 'property_manager':
            queryset = queryset.filter(manager=user)
        return queryset


class AssignPropertyManagerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AssignPropertyManagerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        property_ids = serializer.validated_data['property_ids']
        manager = serializer.validated_data['manager']

        with transaction.atomic():
            updated = Property.objects.filter(
                id__in=property_ids
            ).update(manager=manager)

        return Response(
            {
                "message": "Property manager assigned successfully.",
                "manager_id": manager.id,
                "properties_updated": updated,
            },
            status=status.HTTP_200_OK
        )


class UnitViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing units with full CRUD operations
    """
    queryset = Unit.objects.select_related('property')
    filter_backends = [DjangoFilterBackend,
                       filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['property', 'unit_type', 'occupied_status']
    search_fields = ['name', 'abbreviated_name',
                     'unit_number', 'property__name']
    ordering_fields = ['name', 'unit_number', 'created_at', 'monthly_rent']
    ordering = ['property', 'unit_number']

    def get_serializer_class(self):
        if self.action == 'list':
            return UnitListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return UnitCreateUpdateSerializer
        return UnitDetailSerializer

    def get_queryset(self):
        """Filter queryset based on user permissions if needed"""
        queryset = super().get_queryset()
        return queryset

    @action(detail=False, methods=['get'])
    def available_units(self, request):
        """Get all available/vacant units."""
        available_units = self.get_queryset().filter(
            occupied_status=Unit.OccupiedStatus.VACANT
        ).order_by('unit_number')

        unit_data = []
        for unit in available_units:
            unit_data.append({
                'id': unit.id,
                'name': unit.name,
                'unit_number': unit.unit_number,
                'property': unit.property.name,
                'property_id': unit.property.id,
                'unit_type': unit.unit_type,
                'monthly_rent': str(unit.monthly_rent),
                'deposit_amount': str(unit.deposit_amount),
            })

        return Response({
            'total_available': len(unit_data),
            'available_units': unit_data
        })

    def destroy(self, request, *args, **kwargs):
        """Prevent deletion if unit is occupied"""
        unit = self.get_object()
        if unit.occupied_status == Unit.OccupiedStatus.OCCUPIED:
            return Response({
                'error': 'Cannot delete an occupied unit. Please ensure the unit is vacant first.'
            }, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)
