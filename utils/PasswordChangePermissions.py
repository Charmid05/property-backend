from rest_framework import status, generics, permissions


class UserProfilePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role in [
                'tenant', 'property_manager', 'admin', 'landlord']
        )

    def has_object_permission(self, request, view, obj):
        return obj == request.user
