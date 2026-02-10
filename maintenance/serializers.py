from rest_framework import serializers
from .models import MaintenanceRequest


class MaintenanceRequestSerializer(serializers.ModelSerializer):
    """Serializer for MaintenanceRequest model."""
    
    # Read-only nested fields
    tenant_name = serializers.CharField(
        source='tenant.get_full_name',
        read_only=True
    )
    
    unit_number = serializers.CharField(
        source='unit.unit_number',
        read_only=True,
        allow_null=True
    )
    
    property_name = serializers.CharField(
        source='property.name',
        read_only=True,
        allow_null=True
    )
    
    property_address = serializers.CharField(
        source='property.address',
        read_only=True,
        allow_null=True
    )
    
    assigned_to_name = serializers.CharField(
        source='assigned_to.get_full_name',
        read_only=True,
        allow_null=True
    )
    
    class Meta:
        model = MaintenanceRequest
        fields = [
            'id',
            'tenant',
            'tenant_name',
            'unit',
            'unit_number',
            'property',
            'property_name',
            'property_address',
            'title',
            'description',
            'category',
            'priority',
            'status',
            'reported_date',
            'scheduled_date',
            'completed_date',
            'assigned_to',
            'assigned_to_name',
            'estimated_cost',
            'actual_cost',
            'notes',
            'tenant_notes',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'tenant',
            'reported_date',
            'created_at',
            'updated_at'
        ]
    
    def create(self, validated_data):
        """Create maintenance request with auto-population of unit."""
        # Get tenant's unit automatically if not provided
        tenant = validated_data['tenant']
        
        if not validated_data.get('unit') and hasattr(tenant, 'tenant_profile'):
            validated_data['unit'] = tenant.tenant_profile.unit
        
        return super().create(validated_data)

