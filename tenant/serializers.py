from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from property.models import Unit

from .models import Tenant, TenantDocument
from a_users.models import CustomUser

from rest_framework import serializers
from django.db import transaction
from .models import Tenant, Unit, CustomUser

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Tenant, Unit

User = get_user_model()

class TenantListSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    unit_number = serializers.CharField(source='unit.unit_number', read_only=True)
    property_name = serializers.CharField(source='unit.property.name', read_only=True)
    monthly_rent = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = [
            'id', 'user_name', 'unit_number', 'property_name',
            'status', 'monthly_rent', 'lease_start_date',
            'lease_end_date', 'days_until_lease_expires'
        ]

    def get_monthly_rent(self, obj):
        return obj.monthly_rent


class TenantDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for tenant CRUD operations"""
    user_name = serializers.CharField(
        source='user.get_full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    unit_details = serializers.SerializerMethodField()
    monthly_rent = serializers.ReadOnlyField()
    deposit_amount = serializers.ReadOnlyField()
    total_monthly_charges = serializers.ReadOnlyField()
    is_lease_expired = serializers.ReadOnlyField()

    class Meta:
        model = Tenant
        fields = [
            'id', 'user', 'user_name', 'user_email', 'unit', 'unit_details',
            'status', 'monthly_rent_override', 'deposit_amount_override',
            'lease_start_date', 'lease_end_date',
            'move_in_date', 'move_out_date', 'notes',
            'monthly_rent', 'deposit_amount', 'total_monthly_charges',
            'days_until_lease_expires', 'is_lease_expired',
            'created_at', 'updated_at'
        ]
        read_only_fields = [ 'created_by',
                            'created_at', 'updated_at']

    def get_unit_details(self, obj):
        return {
            'unit_number': obj.unit.unit_number,
            'property_name': obj.unit.property.name,
            'unit_type': obj.unit.unit_type,
        }


class TenantCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating tenants with automatic user creation"""

    # User fields for creating a new user (always required for creation)
    username = serializers.CharField(write_only=True, required=True)
    email = serializers.EmailField(write_only=True, required=True)
    password = serializers.CharField(write_only=True, required=True)
    password2 = serializers.CharField(write_only=True, required=True)
    role = serializers.CharField(write_only=True, default='tenant')
    first_name = serializers.CharField(write_only=True, required=True)
    last_name = serializers.CharField(write_only=True, required=True)
    phone_number = serializers.CharField(
        write_only=True, required=False, allow_blank=True)
    gender = serializers.CharField(
        write_only=True, required=False, allow_blank=True)
    send_welcome_email = serializers.BooleanField(
        write_only=True, default=True)

    class Meta:
        model = Tenant
        fields = [
            'unit', 'status', 'monthly_rent_override',
            'deposit_amount_override',
            'lease_start_date', 'lease_end_date', 'move_in_date',
            'move_out_date', 'notes',
            # User creation fields
            'username', 'email', 'password', 'password2', 'role',
            'first_name', 'last_name', 'phone_number', 'gender',
            'send_welcome_email'
        ]
        # Remove 'user' from fields since we'll create it automatically

    def validate(self, data):
        # Validate lease dates
        if data.get('lease_start_date') and data.get('lease_end_date'):
            if data['lease_end_date'] <= data['lease_start_date']:
                raise serializers.ValidationError(
                    "Lease end date must be after start date."
                )

        # Validate passwords match
        if data['password'] != data['password2']:
            raise serializers.ValidationError(
                {"password": "Passwords must match"}
            )

        # Validate password strength
        try:
            validate_password(data['password'])
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})

        # Validate that the requesting user can create tenants
        request = self.context.get('request')
        if request and request.user:
            if not hasattr(request.user, 'can_create_tenants') or not request.user.can_create_tenants():
                raise serializers.ValidationError(
                    "Only admins and property managers can create tenant accounts."
                )

        return data

    @transaction.atomic
    def create(self, validated_data):
        # Extract user data
        user_data = {
            'username': validated_data.pop('username'),
            'email': validated_data.pop('email'),
            'password': validated_data.pop('password'),
            'role': validated_data.pop('role', 'tenant'),
            'first_name': validated_data.pop('first_name'),
            'last_name': validated_data.pop('last_name'),
            'phone_number': validated_data.pop('phone_number', ''),
            'gender': validated_data.pop('gender', ''),
        }

        # Remove password2 and email flag
        validated_data.pop('password2', None)
        send_welcome_email = validated_data.pop('send_welcome_email', True)

        # Get the requesting user as creator
        request = self.context.get('request')
        created_by = request.user if request else None

        # Create the user
        if hasattr(CustomUser.objects, 'create_tenant'):
            user = CustomUser.objects.create_tenant(
                created_by=created_by,
                **user_data
            )
        else:
            # Fallback if create_tenant method doesn't exist
            password = user_data.pop('password')
            user = CustomUser.objects.create_user(**user_data)
            user.set_password(password)
            user.role = 'tenant'
            user.save()

        # Send welcome email if requested
        if send_welcome_email:
            # Add your email sending logic here
            pass

        # Set the created user to the tenant data
        validated_data['user'] = user

        # Create the tenant
        tenant = Tenant.objects.create(**validated_data)
        if tenant.unit:
            tenant.unit.occupied_status = Unit.OccupiedStatus.OCCUPIED
            tenant.unit.save(update_fields=['occupied_status'])
        return tenant

    def to_representation(self, instance):
        """Custom representation to include user details in response"""
        data = super().to_representation(instance)

        # Add user details to the response
        if instance.user:
            data['user_details'] = {
                'id': instance.user.id,
                'username': instance.user.username,
                'email': instance.user.email,
                'first_name': instance.user.first_name,
                'last_name': instance.user.last_name,
                'phone_number': getattr(instance.user, 'phone_number', ''),
                'role': getattr(instance.user, 'role', ''),
            }

        return data


# For updating existing tenants (without user creation)
class TenantUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating existing tenants only"""

    class Meta:
        model = Tenant
        fields = [
            'unit', 'status', 'monthly_rent_override',
            'deposit_amount_override',
            'lease_start_date', 'lease_end_date', 'move_in_date',
            'move_out_date', 'notes'
        ]

    def validate(self, data):
        if data.get('lease_start_date') and data.get('lease_end_date'):
            if data['lease_end_date'] <= data['lease_start_date']:
                raise serializers.ValidationError(
                    "Lease end date must be after start date."
                )
        return data


class TenantDashboardSerializer(serializers.ModelSerializer):
    """Serializer for dashboard statistics"""
    user_name = serializers.CharField(
        source='user.get_full_name', read_only=True)
    unit_number = serializers.CharField(
        source='unit.unit_number', read_only=True)
    property_name = serializers.CharField(
        source='unit.property.name', read_only=True)

    class Meta:
        model = Tenant
        fields = [
            'id', 'user_name', 'unit_number', 'property_name',
            'status', 'monthly_rent', 'lease_end_date',
            'days_until_lease_expires', 'is_lease_expired'
        ]


class TenantDocumentSerializer(serializers.ModelSerializer):
    """Serializer for tenant documents."""

    uploaded_by_name = serializers.CharField(
        source='uploaded_by.get_full_name', read_only=True)

    class Meta:
        model = TenantDocument
        fields = [
            'id', 'tenant', 'document_type', 'title', 'file',
            'uploaded_by', 'uploaded_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'uploaded_by',
                            'uploaded_by_name', 'created_at', 'updated_at']

    def create(self, validated_data):
        """Set uploaded_by from request context."""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['uploaded_by'] = request.user

        return super().create(validated_data)
