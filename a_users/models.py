from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.core.validators import FileExtensionValidator, RegexValidator
from django.db import models
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from os import path
from uuid import uuid4
from utils.common import EnumWithChoices
from django.apps import apps


def generate_profile_filepath(instance: "CustomUser", filename: str) -> str:
    """Generate unique filepath for user profile pictures."""
    file_extension = path.splitext(filename)[1]
    custom_filename = f"{uuid4()}{file_extension}"
    return f"user_profile/{instance.id}/{custom_filename}"


class CustomUserManager(BaseUserManager):
    """Custom user manager for CustomUser model."""

    def create_user(self, email, username, password=None, created_by=None, **extra_fields):
        """Create and save a regular user with the given email and password."""
        if not email:
            raise ValueError(_('The Email field must be set'))

        email = self.normalize_email(email)
        if extra_fields.get('phone_number') == '':
            extra_fields['phone_number'] = None

        user = self.model(
            email=email,
            username=username,
            created_by=created_by,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        """Create and save a superuser with the given email and password."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, username, password, **extra_fields)

    def create_tenant(self, email, username, password=None, created_by=None, **extra_fields):
        """Create a tenant user specifically."""
        extra_fields.setdefault('role', 'tenant')
        extra_fields.setdefault('is_active', True)

        if created_by and created_by.role not in ['admin', 'property_manager']:
            raise ValueError(
                _('Only admins and property managers can create tenants.'))

        return self.create_user(email, username, password, created_by, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """Custom user model with extended fields and functionality."""

    ROLE_CHOICES = (
        ('tenant', 'Tenant'),
        ('landlord', 'Landlord'),
        ('property_manager', 'Property Manager'),
        ('agent', 'Agent'),
        ('admin', 'Admin'),
        ('caretaker', 'Caretaker'),
    )

    class UserGender(EnumWithChoices):
        MALE = "M"
        FEMALE = "F"
        OTHER = "O"

    class UserStatus(EnumWithChoices):
        ACTIVE = "active"
        INACTIVE = "inactive"
        PENDING = "pending"
        SUSPENDED = "suspended"

    # Basic user information
    email = models.EmailField(_('email address'), unique=True)
    username = models.CharField(_('username'), max_length=150, unique=True)
    first_name = models.CharField(_('first name'), max_length=150, blank=True)
    last_name = models.CharField(_('last name'), max_length=150, blank=True)

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='tenant',
        help_text=_("User's role in the system")
    )

    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_users',
        help_text=_("User who created this account (for tenant creation by admin/property manager)")
    )

    phone_number = models.CharField(
        _('phone number'),
        max_length=15,
        blank=True,
        null=True,
        unique=True,
        help_text=_("Contact phone number"),
        validators=[RegexValidator(
            regex=r"^\+?1?\d{9,15}$",
            message=_("Phone number must be entered in the format: '+254...' or '07...'. Up to 15 digits allowed.")
        )]
    )

    emergency_contact_number = models.CharField(
        _('emergency contact number'),
        max_length=15,
        blank=True,
        null=True,
        help_text=_("Emergency contact number"),
        validators=[RegexValidator(
            regex=r"^\+?1?\d{9,15}$",
            message=_("Phone number must be entered in the format: '+254...' or '07...'. Up to 15 digits allowed.")
        )]
    )

    gender = models.CharField(
        verbose_name=_("gender"),
        max_length=10,
        choices=UserGender.choices(),
        default=UserGender.OTHER.value,
        help_text=_("User's gender")
    )

    identity_number = models.CharField(
        verbose_name=_("identity number"),
        max_length=50,
        null=True,
        blank=True,
        unique=True,
        help_text=_("National ID/Birth Certificate/Passport Number")
    )

    profile = models.ImageField(
        _("profile picture"),
        default="default/user.png",
        upload_to=generate_profile_filepath,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])],
        blank=True,
        null=True,
        help_text=_("User's profile picture")
    )

    is_active = models.BooleanField(default=True, help_text=_("Designates whether this user should be treated as active"))
    is_staff = models.BooleanField(default=False, help_text=_("Designates whether the user can log into the admin site"))

    user_status = models.CharField(
        max_length=20,
        choices=UserStatus.choices(),
        default=UserStatus.ACTIVE.value,
        help_text=_("Current status of the user account")
    )

    password_changed_at = models.DateTimeField(null=True, blank=True, help_text=_("Date and time when password was last changed"))
    password_change_required = models.BooleanField(default=False, help_text=_("Whether user needs to change password on next login"))
    email_verified = models.BooleanField(default=False, help_text=_("Whether user's email address has been verified"))
    email_verification_token = models.CharField(max_length=100, null=True, blank=True, help_text=_("Token for email verification"))

    date_joined = models.DateTimeField(auto_now_add=True, help_text=_("Date when the user account was created"))
    last_login = models.DateTimeField(_("last login"), blank=True, null=True, help_text=_("Date and time of last login"))
    updated_at = models.DateTimeField(auto_now=True, help_text=_("Date and time when the user was last updated"))

    objects = CustomUserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['username']),
            models.Index(fields=['phone_number']),
            models.Index(fields=['role']),
            models.Index(fields=['is_active']),
            models.Index(fields=['user_status']),
            models.Index(fields=['created_by']),
        ]

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.email})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    def get_short_name(self):
        return self.first_name or self.username

    def can_create_tenants(self):
        return self.role in ['admin', 'property_manager'] and self.is_active

    def get_created_tenants(self):
        return self.created_users.filter(role='tenant')

    def set_password(self, raw_password):
        super().set_password(raw_password)
        self.password_changed_at = timezone.now()
        self.password_change_required = False

    def save(self, *args, **kwargs):
        is_new_user = not self.pk
        creator = kwargs.pop('created_by', None)

        if is_new_user:
            if self.password and not self.password.startswith(('pbkdf2_', 'bcrypt', 'argon2')):
                self.set_password(self.password)

            if creator and creator.can_create_tenants():
                self.created_by = creator

            if self.role in ['admin', 'property_manager']:
                self.is_staff = True

            if not self.email_verification_token:
                self.email_verification_token = str(uuid4())

        self.full_clean()
        super().save(*args, **kwargs)

        # Create related UserAccount only after saving user to DB
        if is_new_user:
            UserAccount = apps.get_model('finance', 'UserAccount')
            UserAccount.objects.get_or_create(user=self)

    def clean(self):
        super().clean()
        if self.email:
            self.email = self.email.lower()

        if self.phone_number:
            existing_users = CustomUser.objects.filter(phone_number=self.phone_number)
            if self.pk:
                existing_users = existing_users.exclude(pk=self.pk)
            if existing_users.exists():
                raise ValidationError({'phone_number': _('This phone number is already in use.')})

        if self.created_by and self.role == 'tenant':
            if not self.created_by.can_create_tenants():
                raise ValidationError({'created_by': _('Only active admins and property managers can create tenant accounts.')})

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_property_manager(self):
        return self.role == 'property_manager'

    @property
    def is_tenant(self):
        return self.role == 'tenant'

    @property
    def is_landlord(self):
        return self.role == 'landlord'

    @property
    def is_caretaker(self):
        return self.role == 'caretaker'

    @property
    def is_agent(self):
        return self.role == 'agent'
