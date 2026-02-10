from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils.translation import gettext_lazy as _

from .models import MaintenanceRequest
from .serializers import MaintenanceRequestSerializer


class MaintenanceRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing maintenance requests.
    
    Provides CRUD operations plus custom actions for statistics and cancellation.
    Tenants can only see their own requests, staff can see all.
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = MaintenanceRequestSerializer
    
    def get_queryset(self):
        """Filter queryset based on user role and query parameters."""
        queryset = MaintenanceRequest.objects.select_related(
            'tenant', 'unit', 'property', 'assigned_to'
        )
        
        # Filter by tenant if they're not staff
        if not self.request.user.is_staff:
            queryset = queryset.filter(tenant=self.request.user)
        
        # Apply filters from query params
        status_filter = self.request.query_params.get('status', None)
        priority_filter = self.request.query_params.get('priority', None)
        category_filter = self.request.query_params.get('category', None)
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if priority_filter:
            queryset = queryset.filter(priority=priority_filter)
        if category_filter:
            queryset = queryset.filter(category=category_filter)
        
        return queryset.order_by('-reported_date')
    
    def perform_create(self, serializer):
        """Automatically set tenant to current user."""
        serializer.save(tenant=self.request.user)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Get maintenance statistics for current user.
        
        Returns counts for total, pending, in_progress, completed, and cancelled requests.
        Staff see all requests, tenants see only their own.
        """
        if request.user.is_staff:
            queryset = MaintenanceRequest.objects.all()
        else:
            queryset = MaintenanceRequest.objects.filter(tenant=request.user)
        
        stats = {
            'total_requests': queryset.count(),
            'pending': queryset.filter(status='pending').count(),
            'in_progress': queryset.filter(
                status__in=['assigned', 'in_progress']
            ).count(),
            'completed': queryset.filter(status='completed').count(),
            'cancelled': queryset.filter(status='cancelled').count(),
        }
        
        return Response(stats)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel a maintenance request.
        
        Only the tenant who created the request or staff can cancel it.
        Optionally accepts a 'reason' in the request body.
        """
        maintenance_request = self.get_object()
        
        # Only allow tenant or staff to cancel
        if maintenance_request.tenant != request.user and not request.user.is_staff:
            return Response(
                {'error': _('Permission denied')},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Update status to cancelled
        maintenance_request.status = 'cancelled'
        
        # Add cancellation reason to notes if provided
        reason = request.data.get('reason', '')
        if reason:
            if request.user.is_staff:
                maintenance_request.notes = f"Cancelled by staff: {reason}"
            else:
                maintenance_request.tenant_notes = f"Cancelled by tenant: {reason}"
        
        maintenance_request.save()
        
        serializer = self.get_serializer(maintenance_request)
        return Response(serializer.data)

