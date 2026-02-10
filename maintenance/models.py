from django.db import models
from django.utils.translation import gettext_lazy as _
from a_users.models import CustomUser


class MaintenanceRequest(models.Model):
    """Model for tenant maintenance requests."""
    
    CATEGORY_CHOICES = [
        ('plumbing', _('Plumbing')),
        ('electrical', _('Electrical')),
        ('hvac', _('HVAC')),
        ('appliance', _('Appliance')),
        ('structural', _('Structural')),
        ('pest_control', _('Pest Control')),
        ('cleaning', _('Cleaning')),
        ('other', _('Other')),
    ]
    
    PRIORITY_CHOICES = [
        ('low', _('Low')),
        ('medium', _('Medium')),
        ('high', _('High')),
        ('urgent', _('Urgent')),
    ]
    
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('assigned', _('Assigned')),
        ('in_progress', _('In Progress')),
        ('completed', _('Completed')),
        ('cancelled', _('Cancelled')),
    ]
    
    # Relationships
    tenant = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='maintenance_requests',
        verbose_name=_("Tenant"),
        help_text=_("Tenant who submitted the request")
    )
    
    unit = models.ForeignKey(
        'property.Unit',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='maintenance_requests',
        verbose_name=_("Unit"),
        help_text=_("Unit requiring maintenance")
    )
    
    property = models.ForeignKey(
        'property.Property',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='maintenance_requests',
        verbose_name=_("Property"),
        help_text=_("Property where maintenance is needed")
    )
    
    # Request details
    title = models.CharField(
        max_length=200,
        verbose_name=_("Title"),
        help_text=_("Brief description of the issue")
    )
    
    description = models.TextField(
        verbose_name=_("Description"),
        help_text=_("Detailed description of the maintenance issue")
    )
    
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        verbose_name=_("Category"),
        help_text=_("Type of maintenance required")
    )
    
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='medium',
        verbose_name=_("Priority"),
        help_text=_("Urgency level of the request")
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name=_("Status"),
        help_text=_("Current status of the request")
    )
    
    # Timestamps
    reported_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Reported Date"),
        help_text=_("When the request was submitted")
    )
    
    scheduled_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Scheduled Date"),
        help_text=_("When maintenance is scheduled")
    )
    
    completed_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Completed Date"),
        help_text=_("When maintenance was completed")
    )
    
    # Assignment
    assigned_to = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_maintenance',
        verbose_name=_("Assigned To"),
        help_text=_("Staff member assigned to handle this request")
    )
    
    # Cost tracking
    estimated_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Estimated Cost"),
        help_text=_("Estimated cost of the repair")
    )
    
    actual_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Actual Cost"),
        help_text=_("Actual cost of the repair")
    )
    
    # Notes
    notes = models.TextField(
        blank=True,
        verbose_name=_("Staff Notes"),
        help_text=_("Internal notes for staff")
    )
    
    tenant_notes = models.TextField(
        blank=True,
        verbose_name=_("Tenant Notes"),
        help_text=_("Additional notes from tenant")
    )
    
    # Audit fields
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At")
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At")
    )
    
    class Meta:
        verbose_name = _('Maintenance Request')
        verbose_name_plural = _('Maintenance Requests')
        ordering = ['-reported_date']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['property', 'status']),
            models.Index(fields=['unit', 'status']),
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
            models.Index(fields=['category']),
            models.Index(fields=['-reported_date']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.tenant.get_full_name()} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        """Auto-set property from unit if not set."""
        if self.unit and not self.property:
            self.property = self.unit.property
        super().save(*args, **kwargs)

