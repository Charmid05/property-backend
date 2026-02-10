from django.contrib.auth import authenticate
import traceback
from venv import logger
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from tenant.models import Tenant
from .models import CustomUser

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class UserListSerializer(serializers.ModelSerializer):
    """Simple serializer for admin to view all users."""
    full_name = serializers.ReadOnlyField(source='get_full_name')
    created_by_name = serializers.SerializerMethodField()
    tenant_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'role', 'phone_number', 'is_active', 'user_status',
            'email_verified', 'date_joined', 'created_by_name', 'tenant_count'
        ]
        read_only_fields = ['id', 'date_joined']

    def get_created_by_name(self, obj):
        """Get the name of the user who created this account."""
        if obj.created_by:
            return obj.created_by.get_full_name()
        return None

    def get_tenant_count(self, obj):
        """Get count of tenants created by this user (for admins/property managers)."""
        if obj.can_create_tenants():
            return obj.get_created_tenants().count()
        return None

# some changes to the server


class CustomUserSerializer(serializers.ModelSerializer):
    """Full user serializer for profile data."""
    full_name = serializers.ReadOnlyField(source='get_full_name')
    created_by_info = serializers.SerializerMethodField()
    tenant_info = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'phone_number', 'gender', 'identity_number',
            'emergency_contact_number', 'profile', 'user_status',
            'email_verified', 'password_change_required', 'date_joined',
            'created_by_info', 'tenant_info'
        ]
        read_only_fields = ['id', 'date_joined', 'role', 'created_by_info']

    def get_created_by_info(self, obj):
        """Get information about who created this user."""
        if obj.created_by:
            return {
                'id': obj.created_by.id,
                'name': obj.created_by.get_full_name(),
                'role': obj.created_by.role,
                'email': obj.created_by.email
            }
        return None

    def get_tenant_info(self, obj):
        """Get tenant-specific information if user is a tenant."""
        if obj.role != 'tenant':
            return None

        try:
            tenant = obj.tenant_profile
            return {
                'id': tenant.id,
                'status': tenant.status,
                'lease_start_date': tenant.lease_start_date,
                'lease_end_date': tenant.lease_end_date,
                'monthly_rent': tenant.monthly_rent,
                'is_lease_active': tenant.is_lease_active,
                'days_until_lease_expires': tenant.days_until_lease_expires,
            }

        except Tenant.DoesNotExist:
            return None


class CustomUserCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating users with role validation."""
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(
        choices=CustomUser.ROLE_CHOICES, required=True)

    class Meta:
        model = CustomUser
        fields = [
            'email', 'username', 'password', 'first_name', 'last_name',
            'role', 'phone_number', 'gender', 'identity_number',
            'emergency_contact_number'
        ]

    def validate_email(self, value):
        if CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email is already in use.")
        return value.lower()

    def validate_phone_number(self, value):
        if value and CustomUser.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError(
                "This phone number is already in use.")
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = CustomUser(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for users to update their own profile."""

    class Meta:
        model = CustomUser
        fields = [
            'first_name', 'last_name', 'phone_number', 'profile',
            'gender', 'emergency_contact_number', 'identity_number'
        ]

    def validate_phone_number(self, value):
        if not value:
            return value

        user = self.context['request'].user
        if CustomUser.objects.exclude(id=user.id).filter(phone_number=value).exists():
            raise serializers.ValidationError(
                "This phone number is already in use.")
        return value

    def validate_profile(self, value):
        if value and value.size > 5 * 1024 * 1024:  # 5MB
            raise serializers.ValidationError(
                "Profile picture must be less than 5MB.")
        return value

    def validate_identity_number(self, value):
        if not value:
            return value

        user = self.context['request'].user
        if CustomUser.objects.exclude(id=user.id).filter(identity_number=value).exists():
            raise serializers.ValidationError(
                "This identity number is already in use.")
        return value


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change."""
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)
    confirm_password = serializers.CharField(required=True, write_only=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def validate(self, attrs):
        new_password = attrs.get('new_password')
        confirm_password = attrs.get('confirm_password')

        if new_password != confirm_password:
            raise serializers.ValidationError("New passwords do not match.")

        try:
            validate_password(new_password, self.context['request'].user)
        except DjangoValidationError as e:
            raise serializers.ValidationError(
                {"new_password": list(e.messages)})

        return attrs

    def save(self):
        """Update user password and track the change."""
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    """Login serializer supporting email, phone, or username."""
    identifier = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, data):
        try:
            logger.info(
                f"Validating login data: {data.get('identifier', 'NO_IDENTIFIER')}")

            identifier = data.get('identifier')
            password = data.get('password')

            if not identifier or not password:
                logger.warning("Missing identifier or password")
                raise serializers.ValidationError(
                    "Identifier and password are required.")

            # Use Django's authenticate function
            user = authenticate(
                request=self.context.get('request'),
                username=identifier,  # For compatibility, pass identifier as username
                password=password
            )

            if not user:
                # Try to find user by email or phone if authenticate fails
                UserModel = get_user_model()
                try:
                    if '@' in identifier:
                        logger.info("Identifier appears to be email")
                        user = UserModel.objects.get(email=identifier.lower())
                    elif identifier.isdigit():
                        logger.info("Identifier appears to be phone")
                        user = UserModel.objects.get(phone_number=identifier)
                    else:
                        logger.info("Identifier appears to be username")
                        user = UserModel.objects.get(username=identifier)
                except UserModel.DoesNotExist:
                    logger.info(
                        f"User not found with identifier: {identifier}")
                    raise serializers.ValidationError("Invalid credentials.")

                # Re-authenticate with found user
                if user and not user.check_password(password):
                    logger.warning("Invalid password for user")
                    raise serializers.ValidationError("Invalid credentials.")

            logger.info(f"User found: {user.email}")

            if not user.is_active:
                logger.warning(f"User {user.email} is not active")
                raise serializers.ValidationError("User account is disabled.")

            # Check user_status if it exists
            if hasattr(user, 'user_status') and hasattr(CustomUser, 'UserStatus'):
                if user.user_status == CustomUser.UserStatus.SUSPENDED.value:
                    logger.warning(f"User {user.email} is suspended")
                    raise serializers.ValidationError(
                        "User account is suspended.")

            data['user'] = user
            logger.info("Validation successful")
            return data

        except Exception as e:
            logger.error(f"Validation error: {e}")
            logger.error(f"Validation traceback: {traceback.format_exc()}")
            raise serializers.ValidationError(f"Validation error: {str(e)}")


class RegisterSerializer(serializers.ModelSerializer):
    """User registration serializer for admin, landlord, and property manager roles."""
    password = serializers.CharField(write_only=True, required=True)
    password2 = serializers.CharField(write_only=True, required=True)
    role = serializers.ChoiceField(
        choices=[('admin', 'Admin'), ('landlord', 'Landlord'),
                 ('property_manager', 'Property Manager')],
        required=True,
        help_text="User role (admin, landlord, or property_manager)"
    )

    class Meta:
        model = CustomUser
        fields = [
            'username', 'email', 'password', 'password2', 'role',
            'first_name', 'last_name', 'phone_number', 'gender'
        ]
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True},
            'phone_number': {'required': True},
        }

    def validate(self, data):
        """Validate registration data."""
        # Validate passwords match
        if data['password'] != data['password2']:
            raise serializers.ValidationError(
                {"password": "Passwords must match"})

        # Validate password strength
        try:
            validate_password(data['password'])
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})

        # Validate role
        allowed_roles = ['admin', 'landlord', 'property_manager']
        if data['role'] not in allowed_roles:
            raise serializers.ValidationError(
                {"role": f"Role must be one of {', '.join(allowed_roles)}"}
            )

        # Validate email uniqueness
        if CustomUser.objects.filter(email=data['email'].lower()).exists():
            raise serializers.ValidationError(
                {"email": "This email is already in use."})

        # Validate username uniqueness
        if CustomUser.objects.filter(username=data['username']).exists():
            raise serializers.ValidationError(
                {"username": "This username is already in use."})

        # Validate phone number uniqueness
        if data.get('phone_number') and CustomUser.objects.filter(phone_number=data['phone_number']).exists():
            raise serializers.ValidationError(
                {"phone_number": "This phone number is already in use."})

        return data

    def create(self, validated_data):
        """Create a new user with validated data."""
        validated_data.pop('password2')
        return CustomUser.objects.create_user(**validated_data)
