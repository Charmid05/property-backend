from django.utils.translation import gettext_lazy as _
from rest_framework import permissions
from property.models import Unit
from tenant.models import Tenant

from rest_framework import permissions
from django.contrib.auth import get_user_model
from tenant.models import Unit, Tenant
User = get_user_model()


class IsAdminOrPropertyManager(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Admin, Property Manager, and Tenant are allowed
        return request.user.role in ['admin', 'property_manager', 'tenant', 'landlord']

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        # Admin can access all properties
        if request.user.role == 'admin':
            return True

        # Property manager can access properties they manage
        if request.user.role == 'property_manager':
            # Check if property manager manages this property
            if isinstance(obj, Unit):
                return request.user == obj.property.manager
            if isinstance(obj, Tenant) and obj.unit:
                return request.user == obj.unit.property.manager

        return False


class IsAdminOrLandlord(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in ['admin', 'landlord']

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        return request.user.role in ['admin', 'landlord']


class IsAdminOrLandlordOrPropertyManager(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        return request.user.role in ['admin', 'landlord', 'property_manager']

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        # Admin and landlord can access all properties
        if request.user.role in ['admin', 'landlord']:
            return True

        # Property manager can only access properties they manage
        if request.user.role == 'property_manager':
            return obj.manager == request.user

        return False


class TenantPermissions(permissions.BasePermission):
    """Custom permissions for tenant operations."""

    def has_permission(self, request, view):
        """Check if user has permission to access tenant views."""
        if not request.user.is_authenticated:
            return False

        user = request.user

        # Admins have full access
        if user.is_admin:
            return True

        # Property managers and landlords can manage tenants
        if user.role in ['property_manager', 'landlord', 'admin']:
            return True

        # Tenants can only view their own data
        if user.is_tenant:
            return view.action in ['list', 'retrieve']

        return False

    def has_object_permission(self, request, view, obj):
        """Check if user has permission to access specific tenant object."""
        user = request.user

        # Admins have full access
        if user.is_admin:
            return True
        # Property managers and landlords can access tenants in their properties
        if user.role in ['property_manager', 'landlord']:
            if not obj.unit:
                return False
            return obj.unit.property.manager == user

        # Tenants can only access their own profile (read-only)
        if user.is_tenant:
            if obj.user == user:
                return request.method in permissions.SAFE_METHODS
            return False

        return False
