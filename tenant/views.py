from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.utils.translation import gettext_lazy as _
from django.db.models import Q, Sum, Count
from datetime import date, timedelta
from django.utils import timezone

from datetime import timedelta
from property.models import Property
from django.db.models import Q

from .models import Tenant, TenantDocument
from .serializers import (
    TenantListSerializer,
    TenantDetailSerializer,
    TenantCreateUpdateSerializer,
    TenantDashboardSerializer,
    TenantDocumentSerializer,
    TenantUpdateSerializer
)

from utils.permissions import TenantPermissions
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from datetime import date, timedelta


class TenantViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing tenants with CRUD operations and custom actions
    """
    queryset = Tenant.objects.select_related(
    'user', 'unit__property'
    )
    permission_classes = [TenantPermissions]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # Tenants see only themselves
        if user.is_tenant:
            return queryset.filter(user=user)

        # Property managers / landlords see tenants in properties they manage
        if user.role in ['property_manager', 'landlord'] and not user.is_admin:
            queryset = queryset.filter(
                unit__property__manager=user,
                unit__property__is_active=True
            ).distinct()

        # Optional status filter
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Optional search filter
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(unit__unit_number__icontains=search)
            )

        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return TenantListSerializer
        elif self.action == 'create':
            return TenantCreateUpdateSerializer  # Uses the new serializer for creation
        elif self.action in ['update', 'partial_update']:
            return TenantUpdateSerializer  # Uses separate serializer for updates
        elif self.action in ['dashboard', 'expiring_leases']:
            return TenantDashboardSerializer
        return TenantDetailSerializer

    def perform_create(self, serializer):
        """
        Create tenant with automatic user creation
        No need to set created_by on tenant since user is created within serializer
        """
        # The serializer handles user creation and tenant creation
        serializer.save()

    def create(self, request, *args, **kwargs):
        """
        Override create to provide better error handling for user creation
        """
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            # Handle specific user creation errors
            if 'username' in str(e).lower() and 'already exists' in str(e).lower():
                return Response(
                    {'username': [
                        'A user with that username already exists.']},
                    status=status.HTTP_400_BAD_REQUEST
                )
            elif 'email' in str(e).lower() and 'already exists' in str(e).lower():
                return Response(
                    {'email': ['A user with that email already exists.']},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # Re-raise other exceptions
            raise e

    def update(self, request, *args, **kwargs):
        """
        Override update to ensure we're only updating tenant fields, not user fields
        """
        # Remove any user fields from update data to prevent accidental user updates
        user_fields = [
            'username', 'email', 'password', 'password2', 'role',
            'first_name', 'last_name', 'phone_number', 'gender',
            'send_welcome_email'
        ]

        for field in user_fields:
            if field in request.data:
                request.data.pop(field)

        return super().update(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """
        Get dashboard statistics for tenants
        """
        today = date.today()

        # Get counts
        total_tenants = self.get_queryset().count()
        active_tenants = self.get_queryset().filter(status='active').count()
        pending_tenants = self.get_queryset().filter(status='pending').count()

        # Expiring leases (next 30 days)
        expiring_soon = self.get_queryset().filter(
            lease_end_date__lte=today + timedelta(days=30),
            lease_end_date__gte=today,
            status='active'
        )

        # Recent tenants (last 30 days)
        recent_tenants = self.get_queryset().filter(
            created_at__gte=timezone.now() - timedelta(days=30)
        )

        dashboard_data = {
            'stats': {
                'total_tenants': total_tenants,
                'active_tenants': active_tenants,
                'pending_tenants': pending_tenants,
                'expiring_leases': expiring_soon.count(),
                'recent_tenants': recent_tenants.count(),
            },
            'expiring_leases': TenantDashboardSerializer(
                expiring_soon[:5], many=True
            ).data,
            'recent_tenants': TenantDashboardSerializer(
                recent_tenants.order_by('-created_at')[:5], many=True
            ).data
        }

        return Response(dashboard_data)

    @action(detail=False, methods=['get'])
    def expiring_leases(self, request):
        """
        Get tenants with expiring leases
        """
        days = int(request.query_params.get('days', 30))
        today = date.today()

        expiring_tenants = self.get_queryset().filter(
            lease_end_date__lte=today + timedelta(days=days),
            lease_end_date__gte=today,
            status='active'
        ).order_by('lease_end_date')

        serializer = self.get_serializer(expiring_tenants, many=True)
        return Response({
            'count': expiring_tenants.count(),
            'results': serializer.data
        })

    @action(detail=False, methods=['get'])
    def by_property(self, request):
        """
        Get tenants filtered by property
        """
        property_id = request.query_params.get('property_id')
        if not property_id:
            return Response(
                {'error': 'property_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        tenants = self.get_queryset().filter(
            unit__property_id=property_id
        )

        # Apply status filter if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            tenants = tenants.filter(status=status_filter)

        serializer = TenantListSerializer(tenants, many=True)
        return Response({
            'property_id': property_id,
            'count': tenants.count(),
            'results': serializer.data
        })

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """
        Update tenant status
        """
        tenant = self.get_object()
        new_status = request.data.get('status')

        if new_status not in dict(Tenant.TenantStatus.choices):
            return Response(
                {'error': 'Invalid status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        tenant.status = new_status
        if new_status == 'moved_out' and not tenant.move_out_date:
            tenant.move_out_date = date.today()

            # Mark unit as vacant
            if tenant.unit:
                tenant.unit.occupied_status = Unit.OccupiedStatus.VACANT
                tenant.unit.save(update_fields=['occupied_status'])

        tenant.save()

        serializer = self.get_serializer(tenant)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def update_user_info(self, request, pk=None):
        """
        Update tenant's user information separately
        """
        tenant = self.get_object()
        user = tenant.user

        # Fields that can be updated
        updatable_fields = ['first_name', 'last_name', 'email', 'phone_number']

        updated = False
        for field in updatable_fields:
            if field in request.data:
                setattr(user, field, request.data[field])
                updated = True

        if updated:
            user.save()

        serializer = self.get_serializer(tenant)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        """
        Reset tenant user password (admin/property manager only)
        """
        tenant = self.get_object()
        user = tenant.user

        # Check permissions
        if not request.user.can_create_tenants():
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        new_password = request.data.get('new_password')
        if not new_password:
            return Response(
                {'error': 'new_password is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate password
        try:
            validate_password(new_password, user)
        except ValidationError as e:
            return Response(
                {'new_password': list(e.messages)},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()

        # Optionally send email notification
        send_notification = request.data.get('send_notification', False)
        if send_notification:
            # Add your email sending logic here
            pass

        return Response({'message': 'Password reset successfully'})



class TenantDocumentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing tenant documents."""

    queryset = TenantDocument.objects.select_related('tenant', 'uploaded_by')
    serializer_class = TenantDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['tenant', 'document_type']
    search_fields = ['title', 'tenant__user__first_name',
                     'tenant__user__last_name']
    ordering = ['-created_at']

    def get_queryset(self):
        """Filter documents based on user permissions."""
        user = self.request.user
        queryset = super().get_queryset()

        if user.is_admin:
            return queryset
        elif user.is_property_manager or user.is_landlord:
            return queryset.filter(tenant__created_by=user)
        elif user.is_tenant:
            return queryset.filter(tenant__user=user)
        else:
            return queryset.none()

    def perform_create(self, serializer):
        """Set uploaded_by when creating a document."""
        serializer.save(uploaded_by=self.request.user)
