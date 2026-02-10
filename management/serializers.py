from rest_framework import serializers
from .models import Office
from a_users.models import CustomUser


class OfficeSerializer(serializers.ModelSerializer):
    manager = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        required=True
    )

    class Meta:
        model = Office
        fields = [
            "id",
            "name",
            "manager",
            "description",
            "address",
            "contact_number",
            "email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "created_at",
            "updated_at",
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        
        # Include manager details
        if instance.manager:
            rep["manager"] = {
                "id": instance.manager.id,
                "username": instance.manager.username,
                "email": instance.manager.email,
                "first_name": instance.manager.first_name,
                "last_name": instance.manager.last_name,
                "role": instance.manager.role,
            }
        
        return rep

    def validate_manager(self, value):
        """
        Validate that the manager has appropriate role
        """
        if value and value.role not in ['property_manager', 'admin', 'landlord']:
            raise serializers.ValidationError(
                "Manager must have a role of property_manager, admin, or landlord."
            )
        return value