from datetime import timezone
from django.core.validators import RegexValidator
from django.db import models
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _
from a_users.models import CustomUser
from management.models import Office, PersonalMessage, CommunityMessage
from utils.common import generate_document_filepath, EnumWithChoices

from django.db import models, transaction


class Property(models.Model):
    name = models.CharField(
        max_length=100,
        verbose_name=_("Property name"),
        help_text=_("Unique identity name of the property"),
        unique=True,
    )

    address = models.CharField(
        max_length=200,
        verbose_name=_("Address"),
        help_text=_("Physical address of the property"),
    )

    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Description"),
        help_text=_("Detailed description of the property"),
    )
    office = models.ForeignKey(
        Office,
        on_delete=models.RESTRICT,
        verbose_name=_("Managing Office"),
        help_text=_("Office responsible for managing this property"),
        related_name="properties",
        blank=True,
        null=True,
    )
    manager = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role__in': [
            'property_manager', 'property_manager']},
        related_name="managed_properties",
        verbose_name=_("Property Manager"),
        help_text=_("User assigned to manage this property"),
    )

    picture = models.ImageField(
        verbose_name=_("Property Picture"),
        help_text=_("Main photo of the property"),
        upload_to=generate_document_filepath,
        default="default/apartment-2138949_1920.jpg",
        blank=True,
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active Status"),
        help_text=_("Whether this property is currently active"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
        help_text=_("Date and time when the property was created"),
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At"),
        help_text=_("Date and time when the property was last updated"),
    )

    class Meta:
        verbose_name = _('Property')
        verbose_name_plural = _('Properties')
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['office']),
            models.Index(fields=['manager']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name

    @property
    def vacancy_rate(self):
        total = self.total_units
        if total == 0:
            return 0
        occupied = self.occupied_units_count
        return ((total - occupied) / total) * 100


class Unit(models.Model):
    UNIT_TYPES = (
        ("1B", _("1 Bedroom")),
        ("2B", _("2 Bedroom")),
        ("3B", _("3 Bedroom")),
        ("ST", _("Studio")),
        ("BS", _("Bedsitter")),
        ("SH", _("Single Room")),
        ("OT", _("Other")),
    )

    class OccupiedStatus(models.TextChoices):
        OCCUPIED = "Occupied", _("Occupied")
        VACANT = "Vacant", _("Vacant")
        MAINTENANCE = "Maintenance", _("Maintenance")
        CLOSED = "Closed", _("Closed")
        
    property = models.ForeignKey(
        'Property',
        on_delete=models.CASCADE,
        verbose_name=_("Property"),
        help_text=_("Property this unit belongs to"),
        related_name="units",
    )

    name = models.CharField(
        max_length=100,
        verbose_name=_("Unit Name"),
        help_text=_("Full name of the unit e.g., 'Second Floor - Unit 2'"),
    )

    abbreviated_name = models.CharField(
        max_length=20,
        verbose_name=_("Abbreviated Name"),
        help_text=_("Short name of the unit e.g., 'SF02'"),
    )
    unit_number = models.CharField(
        max_length=50,
        verbose_name=_("Unit Number"),
        help_text=_("Unique identifier for the unit"),
    )

    unit_type = models.CharField(
        max_length=2,
        choices=UNIT_TYPES,
        default="OT",
        verbose_name=_("Unit Type"),
        help_text=_("Type of unit"),
    )

    occupied_status = models.CharField(
        max_length=20,
        choices=OccupiedStatus.choices,
        default=OccupiedStatus.VACANT,
        verbose_name=_("Occupancy Status"),
        help_text=_("Current occupancy status of the unit"),
    )

    monthly_rent = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Monthly Rent"),
        help_text=_("Monthly rent amount for this unit"),
    )

    deposit_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("Deposit Amount"),
        help_text=_("Security deposit for this unit"),
        default=0,
    )

    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Description"),
        help_text=_("Specific details about this unit"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
        help_text=_("Date and time when the unit was created"),
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At"),
        help_text=_("Date and time when the unit was last updated"),
    )

    class Meta:
        verbose_name = _("Unit")
        verbose_name_plural = _("Units")
        ordering = ['property', 'unit_number']
        unique_together = ['property', 'unit_number']
        indexes = [
            models.Index(fields=['property', 'unit_number']),
            models.Index(fields=['occupied_status']),
        ]

    def __str__(self):
        return f"{self.property.name} - {self.unit_number}"

    def clean(self):
        super().clean()
        if self.monthly_rent < 0:
            raise models.ValidationError(
                {'monthly_rent': _("Monthly rent cannot be negative")}
            )
        if self.deposit_amount < 0:
            raise models.ValidationError(
                {'deposit_amount': _("Deposit amount cannot be negative")}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
class PropertyRepair(models.Model):

    # Repair status choices
    class RepairStatus(EnumWithChoices):
        PENDING = "pending"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"
        CANCELLED = "cancelled"

    # Relationships
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="repairs",
        verbose_name=_("Property"),
        help_text=_("Property where the repair is needed"),
    )

    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="repairs",
        verbose_name=_("Unit"),
        help_text=_("Specific unit requiring repair"),
    )

    reported_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="reported_repairs",
        verbose_name=_("Reported By"),
        help_text=_("User who reported the repair issue"),
    )

    # Repair details
    description = models.TextField(
        verbose_name=_("Description"),
        help_text=_("Detailed description of the repair issue"),
    )

    status = models.CharField(
        verbose_name=_("Status"),
        max_length=20,
        choices=RepairStatus.choices(),
        default=RepairStatus.PENDING.value,
        help_text=_("Current status of the repair"),
    )

    # Supporting documentation
    image = models.ImageField(
        verbose_name=_("Repair Image"),
        upload_to="property_repairs/",
        blank=True,
        null=True,
        help_text=_("Photo documenting the repair issue"),
    )

    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
        help_text=_("Date and time when the repair was reported"),
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At"),
        help_text=_("Date and time when the repair was last updated"),
    )

    class Meta:
        verbose_name = _("Property Repair")
        verbose_name_plural = _("Property Repairs")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['property', 'status']),
            models.Index(fields=['unit', 'status']),
            models.Index(fields=['reported_by']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Repair: {self.property.name} - {self.unit.unit_number} ({self.get_status_display()})"

    def clean(self):
        """
        Validate that the unit belongs to the specified property.
        """
        super().clean()
