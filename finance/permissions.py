from rest_framework import permissions


class IsPropertyManagerOrAdmin(permissions.BasePermission):
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admins have full access
        if request.user.role == 'admin':
            return True
        
        # Property managers can view and create
        if request.user.role == 'property_manager':
            return True
        
        # Tenants can only view their own data
        if request.user.role == 'tenant':
            return request.method in permissions.SAFE_METHODS
        
        return False
    
    def has_object_permission(self, request, view, obj):
        # Admins have full access
        if request.user.role == 'admin':
            return True
        
        # Check property manager access
        if request.user.role == 'property_manager':
            # Property manager can access if they manage the property
            if hasattr(obj, 'tenant'):
                return self._manages_tenant_property(request.user, obj.tenant)
            elif hasattr(obj, 'account'):
                if hasattr(obj.account, 'user'):
                    if hasattr(obj.account.user, 'tenant_profile'):
                        return self._manages_tenant_property(
                            request.user, 
                            obj.account.user.tenant_profile
                        )
            return False
        
        # Check tenant access - can only access their own data
        if request.user.role == 'tenant':
            if hasattr(obj, 'tenant'):
                return obj.tenant.user == request.user
            elif hasattr(obj, 'account'):
                return obj.account.user == request.user
        
        return False
    
    def _manages_tenant_property(self, manager, tenant):
        """Check if property manager manages the tenant's property"""
        if not hasattr(tenant, 'property'):
            return False
        
        property_obj = tenant.property
        if not hasattr(property_obj, 'manager'):
            return False
        
        return property_obj.manager == manager


class IsTenantOwner(permissions.BasePermission):
    """
    Permission that ensures tenants can only access their own data
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Admins can access everything
        if request.user.role == 'admin':
            return True
        
        # Property managers can access their tenants' data
        if request.user.role == 'property_manager':
            if hasattr(obj, 'tenant'):
                tenant = obj.tenant
                if hasattr(tenant, 'property') and hasattr(tenant.property, 'manager'):
                    return tenant.property.manager == request.user
        
        # Tenants can only access their own data
        if request.user.role == 'tenant':
            if hasattr(obj, 'tenant'):
                return obj.tenant.user == request.user
            elif hasattr(obj, 'user'):
                return obj.user == request.user
        
        return False