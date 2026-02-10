from django.db.models import Sum
from rest_framework import serializers
from decimal import Decimal
from django.db import transaction
from .models import (
    Payment, Receipt, UserAccount, BillingPeriod, ChargeType, Invoice, InvoiceItem,
    Transaction, UtilityCharge, RentPayment
)


class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
    Base serializer that allows dynamic field inclusion/exclusion
    Usage: ?fields=field1,field2 or ?exclude=field1,field2
    """

    def __init__(self, *args, **kwargs):
        # Don't apply dynamic fields if this is a nested serializer
        if not hasattr(self, '_declared_fields') or kwargs.get('context', {}).get('nested'):
            super().__init__(*args, **kwargs)
            return

        fields = kwargs.pop('fields', None)
        exclude = kwargs.pop('exclude', None)

        # Get fields from request context if available
        request = self.context.get('request') if hasattr(
            self, 'context') else None
        if request:
            fields = fields or request.query_params.get('fields')
            exclude = exclude or request.query_params.get('exclude')

        super().__init__(*args, **kwargs)

        if fields:
            fields = fields.split(',') if isinstance(fields, str) else fields
            allowed = set(fields)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)

        if exclude:
            exclude = exclude.split(',') if isinstance(
                exclude, str) else exclude
            for field_name in exclude:
                self.fields.pop(field_name, None)


class UserAccountSerializer(DynamicFieldsModelSerializer):
    debt_amount = serializers.ReadOnlyField()
    available_credit = serializers.ReadOnlyField()
    is_in_debt = serializers.ReadOnlyField()

    class Meta:
        model = UserAccount
        fields = '__all__'


class BillingPeriodSerializer(DynamicFieldsModelSerializer):
    is_current = serializers.ReadOnlyField()
    days_until_due = serializers.ReadOnlyField()

    class Meta:
        model = BillingPeriod
        fields = '__all__'

class BillingPeriodDetailSerializer(BillingPeriodSerializer):
    """Detailed billing period with invoices and charges"""
    invoices_count = serializers.SerializerMethodField()
    total_billed = serializers.SerializerMethodField()
    total_collected = serializers.SerializerMethodField()
    outstanding_amount = serializers.SerializerMethodField()
    
    def get_invoices_count(self, obj):
        return obj.invoices.count()
    
    def get_total_billed(self, obj):
        return obj.invoices.aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
    
    def get_total_collected(self, obj):
        return obj.invoices.aggregate(
            total=Sum('amount_paid')
        )['total'] or Decimal('0.00')
    
    def get_outstanding_amount(self, obj):
        from django.db.models import F
        result = obj.invoices.aggregate(
            total=Sum(F('total_amount') - F('amount_paid'))
        )['total']
        return result or Decimal('0.00')
    
    class Meta(BillingPeriodSerializer.Meta):
        pass
class ChargeTypeSerializer(DynamicFieldsModelSerializer):
    class Meta:
        model = ChargeType
        fields = '__all__'


class InvoiceItemSerializer(DynamicFieldsModelSerializer):
    line_total = serializers.ReadOnlyField()

    class Meta:
        model = InvoiceItem
        fields = '__all__'

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Quantity must be greater than 0")
        return value


class InvoiceSerializer(DynamicFieldsModelSerializer):
    invoice_number = serializers.ReadOnlyField()
    balance_due = serializers.ReadOnlyField()
    is_overdue = serializers.ReadOnlyField()
    days_overdue = serializers.ReadOnlyField()
    items = InvoiceItemSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = '__all__'


class TransactionSerializer(serializers.ModelSerializer):
    """Regular serializer for transactions - no dynamic fields to avoid issues"""
    transaction_id = serializers.ReadOnlyField()

    class Meta:
        model = Transaction
        fields = '__all__'
        read_only_fields = ('is_reversed', 'reversed_transaction')

    def validate(self, attrs):
        """Validate transaction data"""
        if attrs.get('transaction_type') in ['payment'] and not attrs.get('payment_method'):
            raise serializers.ValidationError(
                "Payment method is required for payments")
        return attrs


class UtilityChargeSerializer(serializers.ModelSerializer):
    """Regular serializer for utility charges - no dynamic fields to avoid issues"""
    class Meta:
        model = UtilityCharge
        fields = '__all__'
        read_only_fields = ('is_billed',)


class RentPaymentSerializer(serializers.ModelSerializer):
    """Updated rent payment serializer with receipt"""
    days_late = serializers.ReadOnlyField()
    is_overdue = serializers.ReadOnlyField()
    total_amount_due = serializers.ReadOnlyField()

    class Meta:
        model = RentPayment
        fields = '__all__'
        read_only_fields = ('transaction', 'processed_by',
                            'is_partial', 'outstanding_amount')


# Nested serializers for complex operations
class InvoiceItemCreateSerializer(serializers.ModelSerializer):
    """Simplified serializer for creating invoice items within invoice"""
    line_total = serializers.ReadOnlyField()

    class Meta:
        model = InvoiceItem
        fields = ['charge_type', 'description',
                  'quantity', 'unit_price', 'line_total']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Quantity must be greater than 0")
        return value


class InvoiceWithItemsSerializer(InvoiceSerializer):
    """Invoice serializer with nested items for creation"""
    items = InvoiceItemCreateSerializer(many=True, required=False)

    class Meta(InvoiceSerializer.Meta):
        pass

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        with transaction.atomic():
            invoice = Invoice.objects.create(**validated_data)

            for item_data in items_data:
                InvoiceItem.objects.create(invoice=invoice, **item_data)

            # Ensure rent item exists after provided items
            invoice.ensure_rent_item()

            # Recalculate totals
            self._calculate_totals(invoice)
            return invoice

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)

        with transaction.atomic():
            # Update invoice fields
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            # Handle items if provided
            if items_data is not None:
                # Delete existing items and create new ones
                instance.items.all().delete()
                for item_data in items_data:
                    InvoiceItem.objects.create(invoice=instance, **item_data)

                # Ensure rent item exists after replacements
                instance.ensure_rent_item()

                # Recalculate totals
                self._calculate_totals(instance)

            return instance

    def _calculate_totals(self, invoice):
        """Calculate invoice totals from items"""
        items = invoice.items.all()
        subtotal = sum(item.line_total for item in items)
        invoice.subtotal = subtotal
        invoice.total_amount = subtotal + invoice.tax_amount
        invoice.save(update_fields=['subtotal', 'total_amount'])





class ProcessRentPaymentSerializer(serializers.Serializer):
    """Serializer for processing rent payments"""
    payment_method = serializers.ChoiceField(
        choices=Transaction.PAYMENT_METHODS)
    reference_number = serializers.CharField(
        max_length=100, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        rent_payment = self.context['rent_payment']
        if rent_payment.status != 'pending':
            raise serializers.ValidationError(
                f"Cannot process payment with status {rent_payment.status}"
            )
        return attrs


class BulkUtilityChargeSerializer(serializers.Serializer):
    """Serializer for bulk utility charge operations"""
    utility_charges = UtilityChargeSerializer(many=True)
    billing_period_id = serializers.IntegerField()

    def validate_billing_period_id(self, value):
        try:
            BillingPeriod.objects.get(id=value)
        except BillingPeriod.DoesNotExist:
            raise serializers.ValidationError("Invalid billing period")
        return value

    def create(self, validated_data):
        charges_data = validated_data['utility_charges']
        billing_period_id = validated_data['billing_period_id']

        charges = []
        with transaction.atomic():
            for charge_data in charges_data:
                charge_data['billing_period_id'] = billing_period_id
                charge = UtilityCharge.objects.create(**charge_data)
                charges.append(charge)

        return {'utility_charges': charges}


# Summary serializers for dashboard/reports
class AccountSummarySerializer(serializers.Serializer):
    """Summary serializer for account overview"""
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    debt_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    available_credit = serializers.DecimalField(
        max_digits=12, decimal_places=2)
    total_invoices = serializers.IntegerField()
    overdue_invoices = serializers.IntegerField()
    pending_payments = serializers.IntegerField()
    last_payment_date = serializers.DateField(allow_null=True)


class MonthlyBillingSummarySerializer(serializers.Serializer):
    """Monthly billing summary"""
    period_name = serializers.CharField()
    total_charges = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_payments = serializers.DecimalField(max_digits=12, decimal_places=2)
    outstanding_balance = serializers.DecimalField(
        max_digits=12, decimal_places=2)
    utility_charges_count = serializers.IntegerField()
    invoices_count = serializers.IntegerField()


# Minimal serializers for list views
class InvoiceListSerializer(serializers.ModelSerializer):
    """Minimal invoice serializer for list views - no dynamic fields"""
    tenant_name = serializers.CharField(
        source='tenant.user.get_full_name', read_only=True)
    balance_due = serializers.ReadOnlyField()
    is_overdue = serializers.ReadOnlyField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'tenant_name', 'issue_date',
            'due_date', 'status', 'total_amount', 'amount_paid',
            'balance_due', 'is_overdue'
        ]


class TransactionListSerializer(serializers.ModelSerializer):
    """Minimal transaction serializer for list views - no dynamic fields"""
    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_id', 'transaction_type', 'amount',
            'payment_method', 'created_at', 'description'
        ]


class RentPaymentListSerializer(serializers.ModelSerializer):
    """Minimal rent payment serializer for list views - no dynamic fields"""
    tenant_name = serializers.CharField(
        source='tenant.user.get_full_name', read_only=True)
    period_name = serializers.CharField(
        source='billing_period.name', read_only=True)

    class Meta:
        model = RentPayment
        fields = [
            'id', 'tenant_name', 'period_name', 'amount',
            'payment_date', 'due_date', 'status', 'is_overdue'
        ]


class ReceiptSerializer(DynamicFieldsModelSerializer):
    """Serializer for receipts"""
    receipt_number = serializers.ReadOnlyField()
    tenant_name = serializers.CharField(
        source='tenant.user.get_full_name',
        read_only=True
    )

    class Meta:
        model = Receipt
        fields = '__all__'
        read_only_fields = ('receipt_number', 'transaction', 'issued_by')


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for general payments"""
    receipt = ReceiptSerializer(read_only=True)

    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ('transaction', 'receipt', 'processed_by', 'status')


class InvoiceDetailSerializer(InvoiceSerializer):
    """Detailed invoice serializer with payments and receipts"""
    items = InvoiceItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    receipts = ReceiptSerializer(many=True, read_only=True)
    transactions = TransactionSerializer(many=True, read_only=True)

    class Meta(InvoiceSerializer.Meta):
        pass
    
class ProcessPaymentSerializer(serializers.Serializer):
    """Serializer for processing payments"""
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        help_text="Amount to pay. If not provided, pays full amount"
    )
    payment_method = serializers.ChoiceField(
        choices=Transaction.PAYMENT_METHODS)
    reference_number = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True
    )
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_amount(self, value):
        if value and value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value


class GenerateInvoiceSerializer(serializers.Serializer):
    """Serializer for generating invoices"""
    tenant_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="List of tenant IDs. If not provided, generates for all active tenants"
    )
    billing_period_id = serializers.IntegerField()
    include_utilities = serializers.BooleanField(default=True)
    auto_send = serializers.BooleanField(
        default=False,
        help_text="Automatically mark invoices as 'sent'"
    )

    def validate_billing_period_id(self, value):
        try:
            period = BillingPeriod.objects.get(id=value)
            if period.is_closed:
                raise serializers.ValidationError(
                    "Cannot generate invoices for closed billing period"
                )
        except BillingPeriod.DoesNotExist:
            raise serializers.ValidationError("Invalid billing period")
        return value


class CloseBillingPeriodSerializer(serializers.Serializer):
    """Serializer for closing billing periods"""
    force = serializers.BooleanField(
        default=False,
        help_text="Force close even if there are pending invoices"
    )
    notes = serializers.CharField(required=False, allow_blank=True)

class AllocatePaymentSerializer(serializers.Serializer):
    """Serializer for allocating payments to invoices"""
    payment_id = serializers.IntegerField()
    invoice_id = serializers.IntegerField()
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        help_text="Amount to allocate. If not provided, allocates maximum possible"
    )

    def validate(self, attrs):
        try:
            payment = Payment.objects.get(id=attrs['payment_id'])
            if payment.status != 'completed':
                raise serializers.ValidationError(
                    "Can only allocate completed payments"
                )
        except Payment.DoesNotExist:
            raise serializers.ValidationError("Invalid payment ID")

        try:
            Invoice.objects.get(id=attrs['invoice_id'])
        except Invoice.DoesNotExist:
            raise serializers.ValidationError("Invalid invoice ID")

        return attrs
class TenantStatementSerializer(serializers.Serializer):
    """Serializer for tenant statement/ledger"""
    tenant_id = serializers.IntegerField()
    tenant_name = serializers.CharField()
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    opening_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    closing_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_charges = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_payments = serializers.DecimalField(max_digits=12, decimal_places=2)
    transactions = TransactionListSerializer(many=True)
    invoices = InvoiceListSerializer(many=True)
    receipts = ReceiptSerializer(many=True)