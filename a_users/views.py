import logging
import traceback
import django
from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from rest_framework import generics, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from finance import models
from utils.generate_acess_token import generate_access_token
from .models import CustomUser
from utils.permissions import IsAdminOrPropertyManager
from .serializers import (
    CustomUserCreateSerializer,
    UserListSerializer,
    CustomUserSerializer,
    ProfileUpdateSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
)

logger = logging.getLogger(__name__)

# Unchanged: LoginView


class LoginView(APIView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request):
        """Login user and return tokens."""
        try:
            logger.info(f"Login attempt with data: {request.data}")

            serializer = self.serializer_class(
                data=request.data, context={'request': request})
            logger.info(f"Serializer created: {serializer}")

            if serializer.is_valid():
                logger.info("Serializer is valid")
                user = serializer.validated_data['user']
                logger.info(f"User found: {user.email}")

                try:
                    tokens = generate_access_token(user)
                    logger.info(f"Tokens generated: {tokens}")
                except Exception as token_error:
                    logger.error(f"Token generation failed: {token_error}")
                    logger.error(
                        f"Token generation traceback: {traceback.format_exc()}")
                    return Response({
                        'message': f'Token generation failed: {str(token_error)}'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                # Update last login
                try:
                    user.last_login = timezone.now()
                    user.save(update_fields=['last_login'])
                    logger.info("Last login updated")
                except Exception as save_error:
                    logger.warning(
                        f"Failed to update last login: {save_error}")

                try:
                    user_data = CustomUserSerializer(user).data
                    logger.info(f"User data serialized: {user_data}")
                except Exception as user_error:
                    logger.error(f"User serialization failed: {user_error}")
                    user_data = {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'role': user.role
                    }  # Fallback

                response_data = {
                    'message': 'Login successful',
                    'user': user_data,
                    'tokens': tokens
                }

                logger.info(f"Sending response: {response_data}")
                return Response(response_data, status=status.HTTP_200_OK)
            else:
                logger.warning(
                    f"Serializer validation failed: {serializer.errors}")
                return Response({
                    'message': serializer.errors.get('non_field_errors', ['Invalid credentials'])[0]
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Unexpected error in login view: {e}")
            logger.error(f"Login view traceback: {traceback.format_exc()}")
            return Response({
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Unchanged: RegisterView


class RegisterView(APIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def post(self, request):
        """Register a new user with role admin, landlord, or property_manager."""
        serializer = self.serializer_class(data=request.data)

        if serializer.is_valid():
            with transaction.atomic():
                user = serializer.save()

                # Generate tokens for auto-login
                refresh = RefreshToken.for_user(user)
                access_token = refresh.access_token

                logger.info(
                    f"New user registered: {user.email} with role {user.role}")

                return Response({
                    'access': str(access_token),
                    'refresh': str(refresh),
                    'user': CustomUserSerializer(user).data,
                    'message': 'Registration successful. Please verify your email to activate your account.'
                }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Blacklist the refresh token to log out the user."""
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response(
                    {"detail": "Refresh token is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            token = RefreshToken(refresh_token)
            token.blacklist()
            logger.info(f"User logged out: {request.user.email}")
            return Response({"message": "Logout successful"}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(
                f"Logout failed for user {request.user.email}: {str(e)}")
            return Response(
                {"detail": "Invalid token or logout failed"},
                status=status.HTTP_400_BAD_REQUEST
            )


class UserViewSet(ModelViewSet):
    """Complete user management viewset with role-based creation."""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter users based on permissions and query params."""
        user = self.request.user
        queryset = CustomUser.objects.select_related(
            'created_by').order_by('-date_joined')

        # Property managers see only users they created + themselves
        if user.role == 'property_manager':
            queryset = queryset.filter(
                models.Q(created_by=user) | models.Q(id=user.id)
            )
        elif user.role != 'admin':
            queryset = queryset.filter(id=user.id)

        # Filter by role if specified
        role_filter = self.request.query_params.get('role')
        if role_filter:
            queryset = queryset.filter(role=role_filter)

        # For tenant_users action
        if self.action == 'tenant_users':
            queryset = queryset.filter(role='tenant')

        return queryset

    def get_serializer_class(self):
        """Use appropriate serializer based on action."""
        if self.action == 'list':
            return UserListSerializer
        elif self.action == 'update_profile':
            return ProfileUpdateSerializer
        elif self.action == 'change_password':
            return ChangePasswordSerializer
        elif self.action in ['create_user', 'create_tenant']:
            return CustomUserCreateSerializer
        return CustomUserSerializer

    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in [
            'create_user', 'create_tenant', 'list', 'retrieve',
            'tenant_users', 'my_created_users', 'deactivate', 'reactivate'
        ]:
            permission_classes = [IsAuthenticated, IsAdminOrPropertyManager]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    # === USER CREATION ===
    @action(detail=False, methods=['post'])
    def create_user(self, request):
        """
        Create a new user with any role.
        - Admin: Can create any role
        - Property Manager: Can create tenant, caretaker, agent
        """
        creator = request.user
        role = request.data.get('role')

        logger.info(f"Creating user with role '{role}' by {creator.email}")

        # Role creation permissions
        allowed_roles = {
            'admin': ['admin'],
            'property_manager': ['tenant', 'caretaker', 'agent'],
        }.get(creator.role, [])

        if creator.role != 'admin' and role not in allowed_roles:
            return Response(
                {'error': f"You can only create users with roles: {', '.join(allowed_roles)}"},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            with transaction.atomic():
                user = serializer.save(created_by=creator)
                logger.info(
                    f"User {user.email} created successfully by {creator.email}")
                return Response({
                    'user': CustomUserSerializer(user).data,
                    'message': f'{role.capitalize()} created successfully'
                }, status=status.HTTP_201_CREATED)
        logger.error(f"User creation failed: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Keep create_tenant for backward compatibility
    @action(detail=False, methods=['post'])
    def create_tenant(self, request):
        """Legacy: Create tenant user (redirects to create_user)"""
        request.data['role'] = 'tenant'
        return self.create_user(request)

    # === OTHER ACTIONS (unchanged but improved logging) ===
    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = CustomUserSerializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_created_users(self, request):
        if request.user.role not in ['admin', 'property_manager']:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        users = CustomUser.objects.filter(created_by=request.user)
        serializer = UserListSerializer(users, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def tenant_users(self, request):
        tenants = self.get_queryset().filter(role='tenant')
        serializer = UserListSerializer(tenants, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        if request.user.role != 'admin':
            return Response({'error': 'Only admins can deactivate users'}, status=status.HTTP_403_FORBIDDEN)
        user = self.get_object()
        user.is_active = False
        user.user_status = CustomUser.UserStatus.INACTIVE.value
        user.save()
        logger.info(f"User {user.email} deactivated by {request.user.email}")
        return Response({'message': f'User {user.email} deactivated'})

    @action(detail=True, methods=['post'])
    def reactivate(self, request, pk=None):
        if request.user.role != 'admin':
            return Response({'error': 'Only admins can reactivate users'}, status=status.HTTP_403_FORBIDDEN)
        user = self.get_object()
        user.is_active = True
        user.user_status = CustomUser.UserStatus.ACTIVE.value
        user.save()
        logger.info(f"User {user.email} reactivated by {request.user.email}")
        return Response({'message': f'User {user.email} reactivated'})
