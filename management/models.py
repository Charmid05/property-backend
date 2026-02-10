from django.db import models

from django.db import models
from a_users.models import CustomUser
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _
from utils.common import EnumWithChoices

class Office(models.Model):
    name = models.CharField(
        max_length=100,
        verbose_name=_("Name"),
        help_text=_("Identity name of the office"),
        unique=True,
    )
    manager = models.ForeignKey(
        CustomUser,
        on_delete=models.RESTRICT,
        verbose_name=_("Manager"),
        help_text=_("Person in charge of the Office"),
    )
    description = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("Description"),
        help_text=_("Details of the Office"),
    )
    address = models.CharField(
        max_length=200,
        verbose_name=_("Address"),
        help_text=_("Physical address of the Office"),
        null=True,
        blank=True,
    )
    contact_number = models.CharField(
        max_length=15,
        validators=[
            RegexValidator(
                regex=r"^\+?\d{9,15}$",
                message=_(
                    "Phone number must be entered in the format: '+254...' or '07...'. "
                    "Up to 15 digits allowed."
                ),
            )
        ],
        help_text=_("Official contact number"),
        blank=True,
        null=True,
    )
    email = models.EmailField(
        max_length=100,
        verbose_name=_("Email"),
        help_text=_("Official email address"),
        blank=True,
        null=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At"),
        help_text=_("Date and time when the entry was last updated"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
        help_text=_("Date and time when the entry was created"),
    )

    class Meta:
        verbose_name = _("Property Office")
        verbose_name_plural = _("Property Offices")

    def __str__(self):
        return self.name


class Community(models.Model):
    name = models.CharField(
        max_length=100,
        verbose_name=_("Name"),
        help_text=_("Name of the community"),
        unique=True,
    )
    description = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Description"),
        help_text=_("Description of the community"),
    )
    social_media_link = models.URLField(
        max_length=200,
        verbose_name=_("Social media link"),
        help_text=_(
            "Link to social media group such as WhatsApp, Telegram etc"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
        help_text=_("Date and time when the community was created"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At"),
        help_text=_("Date and time when the community was last updated"),
    )

    class Meta:
        verbose_name = _("Community")
        verbose_name_plural = _("Communities")

    def __str__(self):
        return self.name


class CommunityMessage(models.Model):
    class MessageCategory(EnumWithChoices):
        GENERAL = "General"
        PAYMENT = "Payment"
        MAINTENANCE = "Maintenance"
        PROMOTION = "Promotion"
        WARNING = "Warning"
        OTHER = "Other"
    communities = models.ManyToManyField(
        Community,
        verbose_name=_("Communities"),
        help_text=_("Communities that receive this message"),
        related_name="messages",
    )
    category = models.CharField(
        max_length=20,
        choices=MessageCategory.choices(),
        default=MessageCategory.GENERAL.value,
        verbose_name=_("Category"),
        help_text=_("Category of the message"),
        null=False,
        blank=False,
    )
    subject = models.CharField(
        max_length=200,
        verbose_name=_("Subject"),
        help_text=_("Message subject"),
        null=False,
        blank=False,
    )
    content = models.CharField(
        max_length=50,
        blank=False,
        null=False,
        verbose_name=_("Content"),
        help_text=_("Message in details"),
    )
    read_by = models.ManyToManyField(
        "tenant.Tenant",
        blank=True,
        verbose_name=_("Read by"),
        help_text=_("Tenants who have read this message"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
        help_text=_("Date and time when the message was created"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At"),
        help_text=_("Date and time when the message was last updated"),
    )


class PersonalMessage(models.Model):
    tenant = models.ForeignKey(
        "tenant.Tenant",
        on_delete=models.CASCADE,
        verbose_name=_("Tenant"),
        help_text=_("Receiver of the message"),
        related_name="messages",
    )
    category = models.CharField(
        max_length=20,
        choices=CommunityMessage.MessageCategory.choices(),
        default=CommunityMessage.MessageCategory.GENERAL.value,
        verbose_name=_("Category"),
        help_text=_("Category of the message"),
    )
    subject = models.CharField(
        max_length=200,
        verbose_name=_("Subject"),
        help_text=_("Message subject"),
        null=False,
        blank=False,
    )
    content = models.CharField(
        max_length=200,
        blank=False,
        null=False,
        verbose_name=_("Content"),
        help_text=_("Message in details"),
    )
    is_read = models.BooleanField(
        verbose_name=_("Is read"), default=False, help_text=_("Message read status")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
        help_text=_("Date and time when the entry was created"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At"),
        help_text=_("Date and time when the entry was last updated"),
    )

    class Meta:
        verbose_name = _("Personal Message")
        verbose_name_plural = _("Personal Messages")

    def __str__(self):
        return f"{self.subject} ({self.category}) - {self.tenant}"
