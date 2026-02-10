from django.db import transaction
from django.db import models
from django.utils.translation import gettext_lazy as _
from utils.common import EnumWithChoices
from a_core.settings import CURRENCY
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal
from datetime import date, timedelta
import uuid
from django.db.models.signals import post_save
from django.dispatch import receiver


class TimeStampedModel(models.Model):
    """Abstract base class with created_at and updated_at fields"""
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("created at"),
        help_text=_("Date and time when the entry was created"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("updated at"),
        help_text=_("Date and time when the entry was updated"),
    )

    class Meta:
        abstract = True


class UserAccount(TimeStampedModel):
    """Financial account for each user"""
    user = models.OneToOneField(
        "a_users.CustomUser",  # Use string reference to avoid circular import
        on_delete=models.CASCADE,
        related_name='account',
        help_text=_("User who owns this account")
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_("Account balance")
    )
    credit_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_("Maximum credit allowed")
    )

    @property
    def debt_amount(self):
        """Return debt amount (positive value)"""
        return abs(self.balance) if self.balance < 0 else Decimal('0.00')

    @property
    def available_credit(self):
        """Calculate available credit"""
        if self.balance >= 0:
            return self.credit_limit
        return max(Decimal('0.00'), self.credit_limit + self.balance)

    @property
    def is_in_debt(self):
        """Check if account is in debt"""
        return self.balance < 0

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - Balance: {self.balance}"

    class Meta:
        verbose_name = _("User Account")
        verbose_name_plural = _("User Accounts")

    # Signal to automatically create UserAccount when a CustomUser is created

    @receiver(post_save, sender="a_users.CustomUser")
    def create_user_account(sender, instance, created, **kwargs):
        """Create a UserAccount when a new CustomUser is created"""
        if created:
            UserAccount.objects.get_or_create(user=instance)

    @receiver(post_save, sender="a_users.CustomUser")
    def save_user_account(sender, instance, **kwargs):
        """Save the UserAccount when the CustomUser is saved"""
        if hasattr(instance, 'account'):
            instance.account.save()


class BillingPeriod(TimeStampedModel):
    PERIOD_TYPES = [
        ('monthly', _('Monthly')),
        ('quarterly', _('Quarterly')),
        ('semi_annual', _('Semi-Annual')),
        ('annual', _('Annual')),
        ('custom', _('Custom')),
    ]

    name = models.CharField(max_length=100, help_text=_(
        "Period name"), default="Monthly Period")
    period_type = models.CharField(
        max_length=20,
        choices=PERIOD_TYPES,
        default='monthly'
    )
    start_date = models.DateField(help_text=_(
        "Billing period start date"), default=date.today())
    end_date = models.DateField(help_text=_(
        "Billing period end date"))
    due_date = models.DateField(help_text=_(
        "Payment due date"))
    is_active = models.BooleanField(default=True)
    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"

    @property
    def is_current(self):
        today = date.today()
        return self.start_date <= today <= self.end_date and not self.is_closed

    @property
    def days_until_due(self):
        """Days until payment is due"""
        return (self.due_date - date.today()).days
    is_closed = models.BooleanField(
        default=False,
        help_text=_("Whether billing period is closed for new charges")
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the period was closed")
    )
    closed_by = models.ForeignKey(
        "a_users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='closed_billing_periods'
    )

    def close_period(self, user):
        """Close the billing period"""
        if self.is_closed:
            raise ValueError("Billing period already closed")
        from django.utils import timezone
        self.is_closed = True
        self.closed_at = timezone.now()
        self.closed_by = user
        self.is_active = False
        self.save()

    def can_add_charges(self):
        """Check if charges can be added to this period"""
        return not self.is_closed and self.is_active


class ChargeType(TimeStampedModel):
    """Types of charges that can be applied"""
    FREQUENCY_CHOICES = [
        ('one_time', _('One Time')),
        ('recurring', _('Recurring')),
        ('usage_based', _('Usage Based')),
    ]

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    is_system_charge = models.BooleanField(
        default=False,
        help_text=_("System-generated charge (rent, utilities)")
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Invoice(TimeStampedModel):
    """Invoice model for billing"""
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('sent', _('Sent')),
        ('paid', _('Paid')),
        ('partial', _('Partially Paid')),
        ('overdue', _('Overdue')),
        ('cancelled', _('Cancelled')),
    ]

    invoice_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False
    )
    tenant = models.ForeignKey(
        'tenant.Tenant',
        on_delete=models.CASCADE,
        related_name='invoices'
    )
    billing_period = models.ForeignKey(
        BillingPeriod,
        on_delete=models.CASCADE,
        related_name='invoices'
    )
    issue_date = models.DateField(default=date.today)
    due_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='draft')

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "a_users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_invoices"
    )

    class Meta:
        ordering = ['-issue_date']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['due_date']),
            models.Index(fields=['billing_period']),
        ]

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        super().save(*args, **kwargs)

    def generate_invoice_number(self):
        """Generate unique invoice number"""
        from django.utils import timezone
        year = timezone.now().year
        month = timezone.now().month
        count = Invoice.objects.filter(
            created_at__year=year,
            created_at__month=month
        ).count() + 1
        return f"INV-{year}{month:02d}-{count:04d}"

    @classmethod
    def generate_for_tenant(cls, tenant, billing_period, created_by=None):
        """
        Generate invoice for a tenant for a billing period
        Includes rent and all utility charges
        """
        from django.db import transaction

        with transaction.atomic():
            # Check if invoice already exists
            existing = cls.objects.filter(
                tenant=tenant,
                billing_period=billing_period
            ).first()

            if existing:
                return existing

            # Create invoice
            invoice = cls.objects.create(
                tenant=tenant,
                billing_period=billing_period,
                due_date=billing_period.due_date,
                created_by=created_by,
                status='draft'
            )

            # Add rent charge from tenant.monthly_rent via helper (idempotent)
            invoice.ensure_rent_item()

            # Add utility charges
            utility_charges = UtilityCharge.objects.filter(
                tenant=tenant,
                billing_period=billing_period,
                is_billed=False
            )

            for utility_charge in utility_charges:
                utility_charge.add_to_invoice(invoice)

            # Calculate totals
            invoice.recalculate_totals()

            return invoice

    def recalculate_totals(self):
        """Recalculate invoice totals from items"""
        items = self.items.all()
        self.subtotal = sum(item.line_total for item in items)
        self.total_amount = self.subtotal + self.tax_amount
        self.save(update_fields=['subtotal', 'total_amount'])

    def ensure_rent_item(self):
        """Ensure a rent line item exists for the tenant for this billing period.
        Uses tenant.monthly_rent as the unit_price. Idempotent.
        """
        # Skip if tenant has no monthly rent info
        tenant = self.tenant
        try:
            rent_amount = tenant.monthly_rent
        except Exception:
            return None

        if rent_amount is None or Decimal(str(rent_amount)) <= Decimal('0.00'):
            return None

        # Find or create the rent charge type
        rent_charge_type, _ = ChargeType.objects.get_or_create(
            name="Monthly Rent",
            defaults={
                'description': 'Monthly rent payment',
                'frequency': 'recurring',
                'is_system_charge': True
            }
        )

        # If an item for Monthly Rent already exists for this invoice, skip
        existing = self.items.filter(charge_type=rent_charge_type).first()
        if existing:
            return existing

        # Create the rent item
        item = InvoiceItem.objects.create(
            invoice=self,
            charge_type=rent_charge_type,
            description=f"Rent for {self.billing_period.name}",
            quantity=Decimal('1.00'),
            unit_price=Decimal(str(rent_amount)),
        )

        # Refresh totals after adding rent
        self.recalculate_totals()
        return item

    @property
    def balance_due(self):
        """Amount still owed on invoice"""
        return self.total_amount - self.amount_paid

    @property
    def is_overdue(self):
        """Check if invoice is overdue"""
        return date.today() > self.due_date and self.status not in ['paid', 'cancelled']

    @property
    def days_overdue(self):
        """Days past due date"""
        if not self.is_overdue:
            return 0
        return (date.today() - self.due_date).days

    def __str__(self):
        return f"{self.invoice_number} - {self.tenant}"


class InvoiceItem(TimeStampedModel):
    """Individual line items on an invoice"""
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='items'
    )
    charge_type = models.ForeignKey(
        ChargeType,
        on_delete=models.CASCADE
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('1.00'),
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        editable=False
    )

    class Meta:
        ordering = ['id']

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} - {self.line_total}"


class Transaction(TimeStampedModel):
    """All financial transactions"""
    TRANSACTION_TYPES = [
        ('payment', _('Payment')),
        ('charge', _('Charge')),
        ('refund', _('Refund')),
        ('adjustment', _('Adjustment')),
        ('penalty', _('Penalty')),
        ('credit', _('Credit')),
    ]

    PAYMENT_METHODS = [
        ('cash', _('Cash')),
        ('bank_transfer', _('Bank Transfer')),
        ('card', _('Card')),
        ('mobile_money', _('Mobile Money')),
        ('check', _('Check')),
        ('other', _('Other')),
    ]
    transaction_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False
    )
    account = models.ForeignKey(
        UserAccount,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(
        max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS,
        blank=True
    )

    # Optional references
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    reference_number = models.CharField(max_length=100, blank=True)

    description = models.TextField()
    processed_by = models.ForeignKey(
        "a_users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name='processed_transactions'
    )

    # For reversals
    reversed_transaction = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reversals'
    )
    is_reversed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', '-created_at']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['invoice']),
        ]

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new and not self.is_reversed:
            self.update_account_balance()

    def update_account_balance(self):
        """Update the account balance based on transaction type"""
        if self.transaction_type in ['payment', 'refund', 'credit']:
            # Increase balance
            self.account.balance += self.amount
        else:
            # Decrease balance (charge, penalty, adjustment)
            self.account.balance -= self.amount

        self.account.save(update_fields=['balance'])

    def reverse(self, user, reason=""):
        """Reverse this transaction"""
        if self.is_reversed:
            raise ValueError("Transaction already reversed")
        # Create reversal transaction
        reversal = Transaction.objects.create(
            account=self.account,
            transaction_type=self.transaction_type,
            amount=self.amount,
            description=f"Reversal of {self.transaction_id}: {reason}",
            processed_by=user,
            reversed_transaction=self,
            is_reversed=True
        )

        self.is_reversed = True
        self.save(update_fields=['is_reversed'])

        if self.transaction_type in ['payment', 'refund', 'credit']:
            self.account.balance -= self.amount
        else:
            self.account.balance += self.amount

        self.account.save(update_fields=['balance'])

        return reversal

    def __str__(self):
        return f"{self.transaction_type.title()} - {self.amount} ({self.transaction_id})"


class UtilityType(models.TextChoices):
    """Predefined utility types"""
    ELECTRICITY = "Electricity", "Electricity"
    WATER = "Water", "Water"
    GAS = "Gas", "Gas"
    INTERNET = "Internet", "Internet"
    GARBAGE = "Garbage Collection", "Garbage Collection"
    SEWER = "Sewer", "Sewer"
    SECURITY = "Security", "Security"
    CLEANING = "Cleaning", "Cleaning"
    PARKING = "Parking", "Parking"
    OTHER = "Other", "Other"
    # This is for extra fees like deposits when a user is moving in
    DEPOSIT = "Deposit", "Deposit"


class UtilityCharge(TimeStampedModel):
    tenant = models.ForeignKey(
        'tenant.Tenant',
        on_delete=models.CASCADE,
        related_name='utility_charges'
    )
    utility_type = models.CharField(
        max_length=20,
        choices=UtilityType.choices,
        help_text=_("Type of utility")
    )
    billing_period = models.ForeignKey(
        BillingPeriod,
        on_delete=models.CASCADE,
        related_name='utility_charges'
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_("Utility charge amount")
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Additional description for the charge")
    )
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Utility bill reference or account number")
    )

    # Processing details
    recorded_by = models.ForeignKey(
        "a_users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name='recorded_utility_charges'
    )
    is_billed = models.BooleanField(
        default=False,
        help_text=_("Whether this charge has been added to an invoice")
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'utility_type']),
            models.Index(fields=['billing_period']),
            models.Index(fields=['is_billed']),
        ]
        unique_together = ['tenant', 'utility_type', 'billing_period']

    def __str__(self):
        return f"{self.tenant} - {self.utility_type} - ${self.amount} ({self.billing_period.name})"

    def add_to_invoice(self, invoice):
        """Add this utility charge to an invoice"""
        if self.is_billed:
            raise ValueError("Utility charge already billed")
        # Get or create utility charge type
        charge_type, _ = ChargeType.objects.get_or_create(
            name=f"{self.utility_type} Bill",
            defaults={
                'description': f'{self.utility_type} utility charges',
                'frequency': 'recurring',
                'is_system_charge': True
            }
        )
        invoice_item = InvoiceItem.objects.create(
            invoice=invoice,
            charge_type=charge_type,
            description=self.description or f"{self.utility_type} - {self.billing_period.name}",
            quantity=Decimal('1.00'),
            unit_price=self.amount
        )
        self.is_billed = True
        self.save(update_fields=['is_billed'])

        return invoice_item


class RentPayment(TimeStampedModel):
    """Dedicated rent payment tracking"""
    PAYMENT_STATUS = [
        ('pending', _('Pending')),
        ('processing', _('Processing')),
        ('completed', _('Completed')),
        ('failed', _('Failed')),
        ('refunded', _('Refunded')),
    ]
    tenant = models.ForeignKey(
        'tenant.Tenant',
        on_delete=models.CASCADE,
        related_name='rent_payments'
    )
    billing_period = models.ForeignKey(
        BillingPeriod,
        on_delete=models.CASCADE,
        related_name='rent_payments'
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='rent_payments',
        null=True,
        blank=True
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payment_date = models.DateField(default=date.today)
    due_date = models.DateField()

    # Status and tracking
    status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS, default='pending')
    payment_method = models.CharField(
        max_length=20,
        choices=Transaction.PAYMENT_METHODS,
        default='bank_transfer'
    )
    reference_number = models.CharField(max_length=100, blank=True)

    # Partial payments
    is_partial = models.BooleanField(default=False)
    outstanding_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Processing details
    processed_by = models.ForeignKey(
        "a_users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name='processed_rent_payments'
    )
    transaction = models.OneToOneField(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rent_payment'
    )

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'billing_period']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['status']),
            models.Index(fields=['due_date']),
        ]
        # One rent payment per tenant per period
        unique_together = ['tenant', 'billing_period']

    @property
    def days_late(self):
        """Calculate days late from due date"""
        if self.payment_date > self.due_date:
            return (self.payment_date - self.due_date).days
        return 0

    @property
    def is_overdue(self):
        """Check if payment is overdue"""
        return date.today() > self.due_date and self.status == 'pending'

    @property
    def total_amount_due(self):
        """Total amount """
        return self.amount

    def process_payment(self, amount_paid=None, processed_by=None, create_receipt=True):
        """
        Process the rent payment with optional partial payment
        """
        if self.status not in ['pending', 'partial']:
            raise ValueError(
                f"Cannot process payment with status {self.status}")

        # Use provided amount or full amount
        payment_amount = amount_paid or self.amount

        if payment_amount > self.total_amount_due:
            raise ValueError("Payment amount exceeds amount due")

        with transaction.atomic():
            # Create transaction
            trans = Transaction.objects.create(
                account=self.tenant.user.account,
                transaction_type='payment',
                amount=payment_amount,
                payment_method=self.payment_method,
                invoice=self.invoice,
                reference_number=self.reference_number,
                description=f"Rent payment for {self.billing_period.name}",
                processed_by=processed_by
            )

            self.transaction = trans

            # Update invoice if exists
            if self.invoice:
                self.invoice.amount_paid += payment_amount

                if self.invoice.amount_paid >= self.invoice.total_amount:
                    self.invoice.status = 'paid'
                else:
                    self.invoice.status = 'partial'
                self.invoice.save()

            # Update rent payment status
            if payment_amount >= self.amount:
                self.status = 'completed'
                self.is_partial = False
                self.outstanding_amount = Decimal('0.00')
            else:
                self.status = 'partial'
                self.is_partial = True
                self.outstanding_amount = self.amount - payment_amount

            self.processed_by = processed_by
            self.save()

            # Create receipt
            receipt = None
            if create_receipt:
                receipt = Receipt.objects.create(
                    transaction=trans,
                    invoice=self.invoice,
                    tenant=self.tenant,
                    amount=payment_amount,
                    payment_date=self.payment_date,
                    payment_method=self.payment_method,
                    amount_allocated_to_invoice=payment_amount,
                    issued_by=processed_by,
                    notes=f"Payment for {self.billing_period.name}"
                )

            return receipt

    def __str__(self):
        return f"Rent Payment - {self.tenant} - {self.billing_period.name} - ${self.amount}"


class Receipt(TimeStampedModel):
    """Receipt for payments"""
    receipt_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False
    )
    transaction = models.OneToOneField(
        Transaction,
        on_delete=models.CASCADE,
        related_name='receipt'
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='receipts',
        null=True,
        blank=True
    )
    tenant = models.ForeignKey(
        'tenant.Tenant',
        on_delete=models.CASCADE,
        related_name='receipts'
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payment_date = models.DateField(default=date.today)
    payment_method = models.CharField(
        max_length=20,
        choices=Transaction.PAYMENT_METHODS
    )

    # Payment allocation
    amount_allocated_to_invoice = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_("Amount applied to specific invoice")
    )
    amount_to_account = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_("Amount credited to account balance")
    )

    notes = models.TextField(blank=True)
    issued_by = models.ForeignKey(
        "a_users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name='issued_receipts'
    )

    class Meta:
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['tenant', '-payment_date']),
            models.Index(fields=['invoice']),
        ]

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = self.generate_receipt_number()
        super().save(*args, **kwargs)

    def generate_receipt_number(self):
        """Generate unique receipt number"""
        from django.utils import timezone
        year = timezone.now().year
        month = timezone.now().month
        count = Receipt.objects.filter(
            created_at__year=year,
            created_at__month=month
        ).count() + 1
        return f"RCP-{year}{month:02d}-{count:04d}"

    def __str__(self):
        return f"{self.receipt_number} - {self.tenant} - {CURRENCY}{self.amount}"


class Payment(TimeStampedModel):
    """General payment model for any invoice or account credit"""
    PAYMENT_STATUS = [
        ('pending', _('Pending')),
        ('completed', _('Completed')),
        ('failed', _('Failed')),
        ('refunded', _('Refunded')),
    ]

    tenant = models.ForeignKey(
        'tenant.Tenant',
        on_delete=models.CASCADE,
        related_name='payments'
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='payments',
        null=True,
        blank=True
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payment_date = models.DateField(default=date.today)
    payment_method = models.CharField(
        max_length=20,
        choices=Transaction.PAYMENT_METHODS
    )
    reference_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS,
        default='pending'
    )

    transaction = models.OneToOneField(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment'
    )
    receipt = models.OneToOneField(
        Receipt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment'
    )

    processed_by = models.ForeignKey(
        "a_users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name='processed_payments'
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['tenant', '-payment_date']),
            models.Index(fields=['invoice']),
            models.Index(fields=['status']),
        ]

    def save(self, *args, **kwargs):
        """Auto-generate reference number if not provided"""
        if not self.reference_number:
            import random
            import string
            from django.utils import timezone
            
            timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
            random_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            self.reference_number = f"AUTO-{timestamp}-{random_code}"
        
        super().save(*args, **kwargs)

    def process(self, processed_by=None):
        """Process the payment and create receipt"""
        if self.status != 'pending':
            raise ValueError(
                f"Cannot process payment with status {self.status}")

        with transaction.atomic():
            # Create transaction
            trans = Transaction.objects.create(
                account=self.tenant.user.account,
                transaction_type='payment',
                amount=self.amount,
                payment_method=self.payment_method,
                invoice=self.invoice,
                reference_number=self.reference_number,
                description=f"Payment {self.reference_number or 'N/A'}",
                processed_by=processed_by
            )

            self.transaction = trans

            # Allocate payment
            amount_to_invoice = Decimal('0.00')
            amount_to_account = Decimal('0.00')

            if self.invoice:
                # Apply to invoice
                remaining_invoice = self.invoice.balance_due
                amount_to_invoice = min(self.amount, remaining_invoice)
                amount_to_account = self.amount - amount_to_invoice

                self.invoice.amount_paid += amount_to_invoice
                if self.invoice.amount_paid >= self.invoice.total_amount:
                    self.invoice.status = 'paid'
                else:
                    self.invoice.status = 'partial'
                self.invoice.save()
            else:
                # Credit to account
                amount_to_account = self.amount

            # Create receipt
            receipt = Receipt.objects.create(
                transaction=trans,
                invoice=self.invoice,
                tenant=self.tenant,
                amount=self.amount,
                payment_date=self.payment_date,
                payment_method=self.payment_method,
                amount_allocated_to_invoice=amount_to_invoice,
                amount_to_account=amount_to_account,
                issued_by=processed_by,
                notes=self.notes
            )
            self.receipt = receipt
            self.status = 'completed'
            self.processed_by = processed_by
            self.save()

            return receipt

    def __str__(self):
        return f"Payment - {self.tenant} - {CURRENCY}{self.amount} ({self.status})"
