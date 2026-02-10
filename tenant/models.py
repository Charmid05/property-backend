from django.db import models
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.forms import ValidationError
from decimal import Decimal
from datetime import date

from a_users.models import CustomUser
from property.models import Unit
from finance.models import UserAccount as Account


class Tenant(models.Model):
    """Tenant model representing a renter in the property management system."""

    class TenantStatus(models.TextChoices):
        ACTIVE = 'active', _('Active')
        INACTIVE = 'inactive', _('Inactive')
        PENDING = 'pending', _('Pending')
        SUSPENDED = 'suspended', _('Suspended')
        MOVED_OUT = 'moved_out', _('Moved Out')

    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='tenant_profile',
        limit_choices_to={'role': 'tenant'},
        help_text=_("User associated with this tenant profile")
    )

    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name='tenants',
        help_text=_("Unit assigned to this tenant")
    )

    status = models.CharField(
        max_length=20,
        choices=TenantStatus.choices,
        default=TenantStatus.PENDING,
        help_text=_("Current status of the tenant")
    )
    monthly_rent_override = models.DecimalField(
        _("Monthly rent override"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        null=True,
        blank=True,
        help_text=_(
            "Override monthly rent amount (if different from unit group default)")
    )

    deposit_amount_override = models.DecimalField(
        _("Security deposit override"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        null=True,
        blank=True,
        help_text=_(
            "Override security deposit amount (if different from unit default)")
    )

    # account = models.OneToOneField(
    #     Account,
    #     on_delete=models.CASCADE,
    #     related_name="tenant",
    #     null=True,
    #     blank=True,
    #     help_text=_("Tenant's financial account")
    # )
    lease_start_date = models.DateField(
        _("Lease start date"),
        help_text=_("Date when the lease begins")
    )

    lease_end_date = models.DateField(
        _("Lease end date"),
        help_text=_("Date when the lease expires"),
        null=True,
        blank=True
    )

    move_in_date = models.DateField(
        _("Move-in date"),
        null=True,
        blank=True,
        help_text=_("Actual date tenant moved into the unit")
    )

    move_out_date = models.DateField(
        _("Move-out date"),
        null=True,
        blank=True,
        help_text=_("Actual date tenant moved out of the unit")
    )

    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_tenants',
        limit_choices_to={'role__in': [
            'admin', 'property_manager', 'landlord']},
        help_text=_(
            "Admin, property manager, or landlord who created this tenant")
    )

    notes = models.TextField(
        _("Notes"),
        blank=True,
        help_text=_("Additional notes about the tenant")
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Tenant')
        verbose_name_plural = _('Tenants')
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                check=models.Q(
                    lease_end_date__gt=models.F('lease_start_date')),
                name='lease_end_after_start'
            ),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.unit}"

    def save(self, *args, **kwargs):
        # """Override save to handle account creation."""
        # is_new = not self.pk

        # # Create account for new tenant if not exists
        # if is_new and not self.account:
        #     self.account = Account.objects.create(
        #         name=f"Tenant Account - {self.user.get_full_name()}",
        #         paybill_number="247247",  # Default paybill or from settings
        #         account_number=f"{self.user.username}_{self.user.id}",
        #         is_active=True,
        #         details=f"Financial account for tenant {self.user.get_full_name()} in unit {self.unit.unit_number}"
        #     )

        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        """Custom validation for the tenant model."""
        super().clean()

        if self.lease_start_date and self.lease_end_date:
            if self.lease_end_date <= self.lease_start_date:
                raise ValidationError({
                    'lease_end_date': _('Lease end date must be after start date.')
                })

    @property
    def monthly_rent(self):
        """Get monthly rent — either overridden or from the unit."""
        if self.monthly_rent_override is not None:
            return self.monthly_rent_override
        return self.unit.monthly_rent  # updated from unit_group

    @property
    def deposit_amount(self):
        """Get deposit amount — either overridden or from the unit."""
        if self.deposit_amount_override is not None:
            return self.deposit_amount_override
        return self.unit.deposit_amount  # remains the same

    @property
    def days_until_lease_expires(self):
        """Calculate how many days are left until lease ends."""
        if not self.lease_end_date:
            return None
        today = date.today()
        return max((self.lease_end_date - today).days, 0)

    @property
    def is_lease_active(self):
        if not self.lease_end_date:
            return True
        return self.lease_start_date <= date.today() <= self.lease_end_date

    @property
    def is_lease_expired(self):
        """Check if the lease is already expired."""
        return bool(self.lease_end_date and self.lease_end_date < date.today())

    @property
    def is_active(self):
        return self.status == self.TenantStatus.ACTIVE

    @property
    def total_monthly_charges(self):
        return self.monthly_rent

    def get_rent_source(self):
        """Return where the rent amount is coming from."""
        if self.monthly_rent_override is not None:
            return "tenant_override"
        return "unit_default"  # updated label

    def get_deposit_source(self):
        """Return where the deposit amount is coming from."""
        if self.deposit_amount_override is not None:
            return "tenant_override"
        return "unit_default"


class TenantDocument(models.Model):
    """Model for storing tenant-related documents."""

    class DocumentType(models.TextChoices):
        LEASE_AGREEMENT = 'lease_agreement', _('Lease Agreement')
        ID_COPY = 'id_copy', _('ID Copy')
        EMPLOYMENT_LETTER = 'employment_letter', _('Employment Letter')
        BANK_STATEMENT = 'bank_statement', _('Bank Statement')
        REFERENCE_LETTER = 'reference_letter', _('Reference Letter')
        OTHER = 'other', _('Other')

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='documents',
        help_text=_("Tenant this document belongs to")
    )

    document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
        help_text=_("Type of document")
    )

    title = models.CharField(
        max_length=255,
        help_text=_("Document title or description")
    )

    file = models.FileField(
        upload_to='tenant_documents/',
        help_text=_("Document file")
    )

    uploaded_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("User who uploaded this document")
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Tenant Document')
        verbose_name_plural = _('Tenant Documents')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tenant} - {self.get_document_type_display()}"
