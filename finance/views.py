from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Sum, Count
from datetime import date
from decimal import Decimal
from django.db import transaction as db_transaction
from django.db.models import Sum, F

from finance.permissions import IsPropertyManagerOrAdmin

from .models import (
    Payment, Receipt, UserAccount, BillingPeriod, ChargeType, Invoice, InvoiceItem,
    Transaction, UtilityCharge, RentPayment
)
from .serializers import (
    BillingPeriodDetailSerializer, InvoiceDetailSerializer, PaymentSerializer, ProcessPaymentSerializer, ReceiptSerializer, TenantStatementSerializer, UserAccountSerializer, BillingPeriodSerializer, ChargeTypeSerializer,
    InvoiceSerializer, InvoiceListSerializer, InvoiceWithItemsSerializer,
    InvoiceItemSerializer, InvoiceItemCreateSerializer, TransactionSerializer, TransactionListSerializer,
    UtilityChargeSerializer, RentPaymentSerializer, RentPaymentListSerializer,
    ProcessRentPaymentSerializer, BulkUtilityChargeSerializer,
    AccountSummarySerializer, MonthlyBillingSummarySerializer, CloseBillingPeriodSerializer, GenerateInvoiceSerializer,
)
from drf_spectacular.utils import extend_schema


class StandardResultsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class BaseViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPropertyManagerOrAdmin]
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend,
                       filters.SearchFilter, filters.OrderingFilter]

    def get_queryset(self):
        """Filter queryset based on user role"""
        queryset = super().get_queryset()
        user = self.request.user

        # Admins see everything
        if user.role == 'admin':
            return queryset

        # Property managers see their properties' data
        if user.role == 'property_manager':
            return self.filter_for_property_manager(queryset, user)

        # Tenants see only their own data
        if user.role == 'tenant':
            return self.filter_for_tenant(queryset, user)

        return queryset.none()

    def filter_for_property_manager(self, queryset, user):
        """Override in subclasses to filter for property managers"""
        return queryset

    def filter_for_tenant(self, queryset, user):
        """Override in subclasses to filter for tenants"""
        return queryset


@extend_schema(tags=["Accounts"])
class UserAccountViewSet(BaseViewSet):
    queryset = UserAccount.objects.all()
    serializer_class = UserAccountSerializer
    filterset_fields = ['balance', 'credit_limit']
    ordering_fields = ['balance', 'created_at']
    ordering = ['-created_at']

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Get account summary with statistics"""
        account = self.get_object()

        # Get related data
        invoices = Invoice.objects.filter(tenant__user__account=account)
        transactions = Transaction.objects.filter(account=account)

        summary_data = {
            'balance': account.balance,
            'debt_amount': account.debt_amount,
            'available_credit': account.available_credit,
            'total_invoices': invoices.count(),
            'overdue_invoices': invoices.filter(
                due_date__lt=date.today(),
                status__in=['sent', 'partial']
            ).count(),
            'pending_payments': RentPayment.objects.filter(
                tenant__user__account=account,
                status='pending'
            ).count(),
            'last_payment_date': transactions.filter(
                transaction_type='payment'
            ).order_by('-created_at').first().created_at.date() if transactions.filter(
                transaction_type='payment'
            ).exists() else None
        }

        serializer = AccountSummarySerializer(summary_data)
        return Response(serializer.data)


@extend_schema(tags=["Receipts"])
class ReceiptViewSet(BaseViewSet):
    queryset = Receipt.objects.select_related(
        'tenant', 'invoice', 'transaction')
    serializer_class = ReceiptSerializer
    filterset_fields = ['tenant', 'invoice', 'payment_method']
    search_fields = ['receipt_number',
                     'tenant__user__first_name', 'tenant__user__last_name']
    ordering_fields = ['payment_date', 'amount', 'created_at']
    ordering = ['-payment_date']

    def filter_for_property_manager(self, queryset, user):
        """Filter receipts for property manager's tenants"""
        from tenant.models import Tenant
        managed_tenant_ids = Tenant.objects.filter(
            unit__property__manager=user
        ).values_list('id', flat=True)
        return queryset.filter(tenant_id__in=managed_tenant_ids)

    def filter_for_tenant(self, queryset, user):
        """Filter receipts for specific tenant"""
        try:
            tenant = user.tenant_profile
            return queryset.filter(tenant=tenant)
        except:
            return queryset.none()

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Generate and download PDF receipt"""
        import logging
        from django.http import HttpResponse
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
        from io import BytesIO
        from a_core.settings import CURRENCY
        
        logger = logging.getLogger(__name__)
        
        try:
            receipt = self.get_object()
            logger.info(f"Generating PDF for receipt {receipt.receipt_number}")
            
            # Create PDF in memory
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72,
                                    topMargin=72, bottomMargin=18)
            
            # Container for the 'Flowable' objects
            elements = []
            
            # Define styles
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=colors.HexColor('#2C3E50'),
                spaceAfter=30,
                alignment=TA_CENTER
            )
            
            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=14,
                textColor=colors.HexColor('#34495E'),
                spaceAfter=12,
            )
            
            # Title
            elements.append(Paragraph("PAYMENT RECEIPT", title_style))
            elements.append(Spacer(1, 12))
            
            # Receipt details
            receipt_info = [
                ['Receipt Number:', receipt.receipt_number],
                ['Payment Date:', receipt.payment_date.strftime('%B %d, %Y')],
                ['Payment Method:', receipt.get_payment_method_display()],
            ]
            
            receipt_table = Table(receipt_info, colWidths=[2*inch, 4*inch])
            receipt_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2C3E50')),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            elements.append(receipt_table)
            elements.append(Spacer(1, 20))
            
            # Tenant information
            elements.append(Paragraph("Tenant Information", heading_style))
            tenant_info = [
                ['Name:', receipt.tenant.user.get_full_name()],
                ['Email:', receipt.tenant.user.email],
                ['Unit:', receipt.tenant.unit.unit_number if receipt.tenant.unit else 'N/A'],
                ['Property:', receipt.tenant.unit.property.name if receipt.tenant.unit else 'N/A'],
            ]
            
            tenant_table = Table(tenant_info, colWidths=[2*inch, 4*inch])
            tenant_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2C3E50')),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(tenant_table)
            elements.append(Spacer(1, 20))
            
            # Payment details
            elements.append(Paragraph("Payment Details", heading_style))
            
            payment_data = [
                ['Description', 'Amount'],
            ]
            
            if receipt.invoice:
                payment_data.append(['Invoice #' + receipt.invoice.invoice_number, f'{CURRENCY}{receipt.amount_allocated_to_invoice:,.2f}'])
            
            if receipt.amount_to_account > 0:
                payment_data.append(['Account Credit', f'{CURRENCY}{receipt.amount_to_account:,.2f}'])
            
            payment_data.append(['', ''])
            payment_data.append(['Total Amount Paid', f'{CURRENCY}{receipt.amount:,.2f}'])
            
            payment_table = Table(payment_data, colWidths=[4*inch, 2*inch])
            payment_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498DB')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -2), 10),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, -1), (-1, -1), 12),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ECF0F1')),
                ('GRID', (0, 0), (-1, -2), 0.5, colors.grey),
                ('BOX', (0, -1), (-1, -1), 2, colors.HexColor('#2C3E50')),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            elements.append(payment_table)
            elements.append(Spacer(1, 20))
            
            # Notes
            if receipt.notes:
                elements.append(Paragraph("Notes", heading_style))
                notes_style = ParagraphStyle('Notes', parent=styles['Normal'], fontSize=10)
                elements.append(Paragraph(receipt.notes, notes_style))
                elements.append(Spacer(1, 20))
            
            # Footer
            footer_style = ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontSize=9,
                textColor=colors.grey,
                alignment=TA_CENTER
            )
            elements.append(Spacer(1, 30))
            elements.append(Paragraph("Thank you for your payment!", footer_style))
            elements.append(Paragraph(f"Transaction ID: {receipt.transaction.transaction_id}", footer_style))
            
            # Build PDF
            doc.build(elements)
            
            # Get PDF from buffer
            pdf = buffer.getvalue()
            buffer.close()
        
            # Create response
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="receipt_{receipt.receipt_number}.pdf"'
            response['Access-Control-Expose-Headers'] = 'Content-Disposition'
            response.write(pdf)
            
            logger.info(f"PDF generated successfully for receipt {receipt.receipt_number}")
            return response
            
        except Exception as e:
            logger.error(f"Error generating PDF for receipt {pk}: {str(e)}", exc_info=True)
            return Response(
                {
                    'error': 'Failed to generate PDF',
                    'detail': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(tags=["Billing"])
class BillingPeriodViewSet(BaseViewSet):
    queryset = BillingPeriod.objects.all()
    serializer_class = BillingPeriodSerializer
    filterset_fields = ['period_type', 'is_active']
    search_fields = ['name']
    ordering_fields = ['start_date', 'end_date', 'due_date']
    ordering = ['-start_date']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return BillingPeriodDetailSerializer
        return BillingPeriodSerializer

    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current active billing period"""
        today = date.today()
        try:
            # Get the most recent active billing period that covers today
            current_period = BillingPeriod.objects.filter(
                start_date__lte=today,
                end_date__gte=today,
                is_active=True
            ).order_by('-start_date').first()

            if not current_period:
                return Response(
                    {'detail': 'No current billing period found'},
                    status=status.HTTP_404_NOT_FOUND
                )

            serializer = self.get_serializer(current_period)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {'detail': f'Error retrieving billing period: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Get billing period summary"""
        period = self.get_object()

        utility_charges = UtilityCharge.objects.filter(billing_period=period)
        invoices = Invoice.objects.filter(billing_period=period)
        payments = RentPayment.objects.filter(billing_period=period)

        total_charges = utility_charges.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

        total_payments = payments.filter(
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        outstanding_balance = invoices.aggregate(
            total=Sum('total_amount') - Sum('amount_paid')
        )['total'] or Decimal('0.00')

        summary_data = {
            'period_name': period.name,
            'total_charges': total_charges,
            'total_payments': total_payments,
            'outstanding_balance': outstanding_balance,
            'utility_charges_count': utility_charges.count(),
            'invoices_count': invoices.count()
        }

        serializer = MonthlyBillingSummarySerializer(summary_data)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Close a billing period"""
        period = self.get_object()
        serializer = CloseBillingPeriodSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        force = serializer.validated_data.get('force', False)

        # Check for pending invoices
        if not force:
            pending_invoices = Invoice.objects.filter(
                billing_period=period,
                status__in=['draft', 'sent', 'partial']
            ).count()

            if pending_invoices > 0:
                return Response(
                    {
                        'error': f'Cannot close period with {pending_invoices} pending invoices',
                        'pending_invoices': pending_invoices,
                        'hint': 'Use force=true to close anyway'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        try:
            period.close_period(request.user)
            return Response({
                'status': 'Billing period closed successfully',
                'period': BillingPeriodSerializer(period).data
            })
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def generate_invoices(self, request, pk=None):
        """Generate invoices for all tenants in this billing period"""
        period = self.get_object()
        serializer = GenerateInvoiceSerializer(data={
            **request.data,
            'billing_period_id': period.id
        })

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if not period.can_add_charges():
            return Response(
                {'error': 'Cannot generate invoices for closed billing period'},
                status=status.HTTP_400_BAD_REQUEST
            )

        tenant_ids = serializer.validated_data.get('tenant_ids')
        auto_send = serializer.validated_data.get('auto_send', False)

        # Get tenants
        from tenant.models import Tenant
        if tenant_ids:
            tenants = Tenant.objects.filter(id__in=tenant_ids, is_active=True)
        else:
            tenants = Tenant.objects.filter(is_active=True)

        invoices_created = []
        errors = []

        for tenant in tenants:
            try:
                invoice = Invoice.generate_for_tenant(
                    tenant=tenant,
                    billing_period=period,
                    created_by=request.user
                )

                if auto_send and invoice.status == 'draft':
                    invoice.status = 'sent'
                    invoice.save()

                invoices_created.append(invoice)
            except Exception as e:
                errors.append({
                    'tenant_id': tenant.id,
                    'tenant_name': tenant.user.get_full_name(),
                    'error': str(e)
                })

        return Response({
            'status': 'Invoice generation completed',
            'invoices_created': len(invoices_created),
            'errors': errors,
            'invoices': InvoiceListSerializer(invoices_created, many=True).data
        })


class ChargeTypeViewSet(BaseViewSet):
    queryset = ChargeType.objects.all()
    serializer_class = ChargeTypeSerializer
    filterset_fields = ['frequency', 'is_system_charge', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


@extend_schema(tags=["Invoices"])
class InvoiceViewSet(BaseViewSet):
    queryset = Invoice.objects.select_related(
        'tenant', 'billing_period').prefetch_related('items')
    filterset_fields = ['status', 'tenant', 'billing_period']
    search_fields = ['invoice_number',
                     'tenant__user__first_name', 'tenant__user__last_name']
    ordering_fields = ['issue_date', 'due_date', 'total_amount']
    ordering = ['-issue_date']

    def get_serializer_class(self):
        if self.action == 'list':
            return InvoiceListSerializer
        elif self.action == 'retrieve':
            return InvoiceDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return InvoiceWithItemsSerializer
        return InvoiceSerializer

    def filter_for_property_manager(self, queryset, user):
        """Filter invoices for property manager's tenants"""
        from tenant.models import Tenant
        managed_tenant_ids = Tenant.objects.filter(
            unit__property__manager=user
        ).values_list('id', flat=True)
        return queryset.filter(tenant_id__in=managed_tenant_ids)

    def filter_for_tenant(self, queryset, user):
        """Filter invoices for specific tenant"""
        try:
            tenant = user.tenant_profile
            return queryset.filter(tenant=tenant)
        except:
            return queryset.none()

    def get_queryset(self):
        queryset = super().get_queryset()

        # Additional filters
        if self.request.query_params.get('overdue') == 'true':
            queryset = queryset.filter(
                due_date__lt=date.today(),
                status__in=['sent', 'partial']
            )

        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if date_from:
            queryset = queryset.filter(issue_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(issue_date__lte=date_to)

        return queryset

    @action(detail=True, methods=['get'])
    def tenant_utility_charges(self, request, pk=None):
        """Get unbilled utility charges for the invoice's tenant and billing period"""
        invoice = self.get_object()

        unbilled_charges = UtilityCharge.objects.filter(
            tenant=invoice.tenant,
            billing_period=invoice.billing_period,
            is_billed=False
        )

        serializer = UtilityChargeSerializer(unbilled_charges, many=True)
        return Response({
            'utility_charges': serializer.data,
            'count': unbilled_charges.count()
        })

    @action(detail=True, methods=['post'])
    def add_utility_charges(self, request, pk=None):
        """Add multiple utility charges to an invoice"""
        invoice = self.get_object()

        if invoice.status not in ['draft', 'sent']:
            return Response(
                {'error': 'Cannot modify paid or cancelled invoices'},
                status=status.HTTP_400_BAD_REQUEST
            )

        utility_charge_ids = request.data.get('utility_charge_ids', [])

        if not utility_charge_ids:
            return Response(
                {'error': 'utility_charge_ids is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        added_charges = []
        errors = []

        with db_transaction.atomic():
            for charge_id in utility_charge_ids:
                try:
                    charge = UtilityCharge.objects.get(id=charge_id)

                    # Verify charge belongs to same tenant and period
                    if charge.tenant != invoice.tenant:
                        errors.append({
                            'charge_id': charge_id,
                            'error': 'Charge does not belong to invoice tenant'
                        })
                        continue

                    if charge.billing_period != invoice.billing_period:
                        errors.append({
                            'charge_id': charge_id,
                            'error': 'Charge does not belong to invoice billing period'
                        })
                        continue

                    if charge.is_billed:
                        errors.append({
                            'charge_id': charge_id,
                            'error': 'Charge already billed'
                        })
                        continue

                    # Add charge to invoice
                    charge.add_to_invoice(invoice)
                    added_charges.append(charge)

                except UtilityCharge.DoesNotExist:
                    errors.append({
                        'charge_id': charge_id,
                        'error': 'Utility charge not found'
                    })

            # Recalculate invoice totals
            if added_charges:
                invoice.recalculate_totals()

        return Response({
            'status': f'Added {len(added_charges)} utility charges',
            'added_count': len(added_charges),
            'errors': errors,
            'invoice': InvoiceSerializer(invoice).data
        })

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """Mark invoice as sent"""
        invoice = self.get_object()
        if invoice.status == 'draft':
            invoice.status = 'sent'
            invoice.save(update_fields=['status'])
            return Response({'status': 'Invoice sent'})
        return Response(
            {'error': 'Invoice must be in draft status'},
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel invoice"""
        invoice = self.get_object()
        if invoice.status in ['draft', 'sent']:
            invoice.status = 'cancelled'
            invoice.save(update_fields=['status'])
            return Response({'status': 'Invoice cancelled'})
        return Response(
            {'error': 'Cannot cancel paid or partially paid invoice'},
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=False, methods=['get'])
    def overdue(self, request):
        """Get overdue invoices"""
        overdue_invoices = self.get_queryset().filter(
            due_date__lt=date.today(),
            status__in=['sent', 'partial']
        )

        page = self.paginate_queryset(overdue_invoices)
        if page is not None:
            serializer = InvoiceListSerializer(
                page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = InvoiceListSerializer(
            overdue_invoices, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_charge(self, request, pk=None):
        """Add a charge/item to an invoice"""
        invoice = self.get_object()

        if invoice.status not in ['draft', 'sent']:
            return Response(
                {'error': 'Cannot modify paid or cancelled invoices'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = InvoiceItemCreateSerializer(data=request.data)
        if serializer.is_valid():
            item = serializer.save(invoice=invoice)
            invoice.recalculate_totals()

            return Response({
                'status': 'Charge added successfully',
                'item': InvoiceItemSerializer(item).data,
                'invoice': InvoiceSerializer(invoice).data
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['delete'])
    def remove_charge(self, request, pk=None):
        """Remove a charge/item from an invoice"""
        invoice = self.get_object()
        item_id = request.data.get('item_id')

        if not item_id:
            return Response(
                {'error': 'item_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if invoice.status not in ['draft', 'sent']:
            return Response(
                {'error': 'Cannot modify paid or cancelled invoices'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            item = invoice.items.get(id=item_id)
            item.delete()
            invoice.recalculate_totals()

            return Response({
                'status': 'Charge removed successfully',
                'invoice': InvoiceSerializer(invoice).data
            })
        except InvoiceItem.DoesNotExist:
            return Response(
                {'error': 'Item not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['post'])
    def apply_payment(self, request, pk=None):
        """Apply a payment to this invoice"""
        invoice = self.get_object()
        serializer = ProcessPaymentSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        amount = serializer.validated_data.get('amount') or invoice.balance_due

        if amount > invoice.balance_due:
            return Response(
                {'error': f'Payment amount ({amount}) exceeds balance due ({invoice.balance_due})'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with db_transaction.atomic():
                # Create payment
                payment = Payment.objects.create(
                    tenant=invoice.tenant,
                    invoice=invoice,
                    amount=amount,
                    payment_method=serializer.validated_data['payment_method'],
                    reference_number=serializer.validated_data.get(
                        'reference_number', ''),
                    notes=serializer.validated_data.get('notes', '')
                )

                # Process payment
                receipt = payment.process(processed_by=request.user)

                return Response({
                    'status': 'Payment applied successfully',
                    'payment': PaymentSerializer(payment).data,
                    'receipt': ReceiptSerializer(receipt).data,
                    'invoice': InvoiceSerializer(invoice).data
                })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'])
    def payment_history(self, request, pk=None):
        """Get payment history for an invoice"""
        invoice = self.get_object()

        payments = invoice.payments.all()
        receipts = invoice.receipts.all()
        transactions = invoice.transactions.all()

        return Response({
            'invoice': InvoiceSerializer(invoice).data,
            'payments': PaymentSerializer(payments, many=True).data,
            'receipts': ReceiptSerializer(receipts, many=True).data,
            'transactions': TransactionSerializer(transactions, many=True).data
        })


class InvoiceItemViewSet(BaseViewSet):
    queryset = InvoiceItem.objects.select_related('invoice', 'charge_type')
    serializer_class = InvoiceItemSerializer
    filterset_fields = ['invoice', 'charge_type']
    ordering_fields = ['line_total', 'created_at']
    ordering = ['id']


@extend_schema(tags=["Transactions"])
class TransactionViewSet(BaseViewSet):
    queryset = Transaction.objects.select_related('account', 'invoice')
    filterset_fields = ['transaction_type',
                        'payment_method', 'account', 'invoice']
    search_fields = ['transaction_id', 'reference_number', 'description']
    ordering_fields = ['created_at', 'amount']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return TransactionListSerializer
        return TransactionSerializer

    def filter_for_property_manager(self, queryset, user):
        """Filter transactions for property manager's tenants"""
        from tenant.models import Tenant
        managed_tenants = Tenant.objects.filter(
            unit__property__manager=user
        )
        account_ids = managed_tenants.values_list(
            'user__account__id', flat=True)
        return queryset.filter(account_id__in=account_ids)

    def filter_for_tenant(self, queryset, user):
        """Filter transactions for specific tenant"""
        return queryset.filter(account__user=user)

    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        """Reverse a transaction"""
        transaction_obj = self.get_object()
        reason = request.data.get('reason', '')

        try:
            reversal = transaction_obj.reverse(request.user, reason)
            serializer = TransactionSerializer(
                reversal, context={'request': request})
            return Response(serializer.data)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class UtilityChargeViewSet(BaseViewSet):
    queryset = UtilityCharge.objects.select_related('tenant', 'billing_period')
    serializer_class = UtilityChargeSerializer
    filterset_fields = ['utility_type',
                        'tenant', 'billing_period', 'is_billed']
    search_fields = ['description', 'reference_number']
    ordering_fields = ['amount', 'created_at']
    ordering = ['-created_at']

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Create multiple utility charges"""
        serializer = BulkUtilityChargeSerializer(
            data=request.data, context={'request': request})
        if serializer.is_valid():
            result = serializer.save()
            return Response(
                {'created': len(result['utility_charges'])},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def add_to_invoice(self, request, pk=None):
        """Add utility charge to an invoice"""
        utility_charge = self.get_object()
        invoice_id = request.data.get('invoice_id')

        if not invoice_id:
            return Response(
                {'error': 'invoice_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            invoice = Invoice.objects.get(id=invoice_id)
            invoice_item = utility_charge.add_to_invoice(invoice)

            return Response({
                'status': 'Added to invoice',
                'invoice_item_id': invoice_item.id
            })
        except Invoice.DoesNotExist:
            return Response(
                {'error': 'Invoice not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'])
    def bulk_add_to_period(self, request):
        """Add multiple utility charges to a billing period"""
        billing_period_id = request.data.get('billing_period_id')
        charges = request.data.get('charges', [])

        if not billing_period_id:
            return Response(
                {'error': 'billing_period_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            period = BillingPeriod.objects.get(id=billing_period_id)

            if not period.can_add_charges():
                return Response(
                    {'error': 'Cannot add charges to closed billing period'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            created_charges = []
            errors = []

            with db_transaction.atomic():
                for charge_data in charges:
                    try:
                        charge = UtilityCharge.objects.create(
                            billing_period=period,
                            recorded_by=request.user,
                            **charge_data
                        )
                        created_charges.append(charge)
                    except Exception as e:
                        errors.append({
                            'charge_data': charge_data,
                            'error': str(e)
                        })

            return Response({
                'status': 'Bulk operation completed',
                'charges_created': len(created_charges),
                'errors': errors,
                'charges': UtilityChargeSerializer(created_charges, many=True).data
            })

        except BillingPeriod.DoesNotExist:
            return Response(
                {'error': 'Billing period not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['post'])
    def bulk_bill(self, request):
        """Add multiple utility charges to their respective tenant invoices"""
        billing_period_id = request.data.get('billing_period_id')
        utility_charge_ids = request.data.get('utility_charge_ids', [])

        if not billing_period_id:
            return Response(
                {'error': 'billing_period_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            period = BillingPeriod.objects.get(id=billing_period_id)

            # Get utility charges
            if utility_charge_ids:
                charges = UtilityCharge.objects.filter(
                    id__in=utility_charge_ids,
                    billing_period=period,
                    is_billed=False
                )
            else:
                # Bill all unbilled charges for this period
                charges = UtilityCharge.objects.filter(
                    billing_period=period,
                    is_billed=False
                )

            billed_count = 0
            errors = []

            with db_transaction.atomic():
                for charge in charges:
                    try:
                        # Get or create invoice for tenant
                        invoice, created = Invoice.objects.get_or_create(
                            tenant=charge.tenant,
                            billing_period=period,
                            defaults={
                                'due_date': period.due_date,
                                'created_by': request.user,
                                'status': 'draft'
                            }
                        )

                        # Add charge to invoice
                        charge.add_to_invoice(invoice)
                        invoice.recalculate_totals()
                        billed_count += 1

                    except Exception as e:
                        errors.append({
                            'charge_id': charge.id,
                            'tenant': str(charge.tenant),
                            'error': str(e)
                        })

            return Response({
                'status': 'Bulk billing completed',
                'charges_billed': billed_count,
                'errors': errors
            })

        except BillingPeriod.DoesNotExist:
            return Response(
                {'error': 'Billing period not found'},
                status=status.HTTP_404_NOT_FOUND
            )


@extend_schema(tags=["Rent Payments"])
class RentPaymentViewSet(BaseViewSet):
    queryset = RentPayment.objects.select_related(
        'tenant', 'billing_period', 'invoice', 'transaction', 'processed_by'
    )
    serializer_class = RentPaymentSerializer
    filterset_fields = ['status', 'tenant', 'invoice', 'payment_method']
    search_fields = ['tenant__user__first_name', 'tenant__user__last_name']
    ordering_fields = ['payment_date', 'due_date', 'amount', 'created_at']
    ordering = ['-payment_date']

    def filter_for_property_manager(self, queryset, user):
        """Filter rent payments for property manager's tenants"""
        from tenant.models import Tenant
        managed_tenant_ids = Tenant.objects.filter(
            unit__property__manager=user
        ).values_list('id', flat=True)
        return queryset.filter(tenant_id__in=managed_tenant_ids)

    def filter_for_tenant(self, queryset, user):
        """Filter rent payments for specific tenant"""
        try:
            tenant = user.tenant_profile
            return queryset.filter(tenant=tenant)
        except AttributeError:
            return queryset.none()

    @action(detail=True, methods=['post'])
    def pay_remaining(self, request, pk=None):
        """Pay remaining balance on a partial payment"""
        rent_payment = self.get_object()

        if not rent_payment.is_partial:
            return Response(
                {'error': 'This is not a partial payment'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ProcessPaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Process remaining amount
            receipt = rent_payment.process_payment(
                amount_paid=rent_payment.outstanding_amount,
                processed_by=request.user
            )

            return Response({
                'status': 'Remaining balance paid successfully',
                'rent_payment': RentPaymentSerializer(rent_payment).data,
                'receipt': ReceiptSerializer(receipt).data if receipt else None
            })
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """Process rent payment"""
        rent_payment = self.get_object()

        serializer = ProcessRentPaymentSerializer(
            data=request.data,
            context={'request': request, 'rent_payment': rent_payment}
        )

        if serializer.is_valid():
            # Update payment details
            rent_payment.payment_method = serializer.validated_data['payment_method']
            rent_payment.reference_number = serializer.validated_data.get(
                'reference_number', '')
            rent_payment.notes = serializer.validated_data.get('notes', '')

            try:
                rent_payment.process_payment(processed_by=request.user)
                return Response({'status': 'Payment processed successfully'})
            except ValueError as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def overdue(self, request):
        """Get all overdue rent payments"""
        qs = self.get_queryset().filter(
            status='pending',
            due_date__lt=date.today()
        )

        # Apply role-based filtering
        user = request.user
        if user.role == 'property_manager':
            qs = self.filter_for_property_manager(qs, user)
        elif user.role == 'tenant':
            qs = self.filter_for_tenant(qs, user)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = RentPaymentListSerializer(
                page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = RentPaymentListSerializer(
            qs, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get pending rent payments"""
        qs = self.get_queryset().filter(status='pending')

        # Role-based filtering
        user = request.user
        if user.role == 'property_manager':
            qs = self.filter_for_property_manager(qs, user)
        elif user.role == 'tenant':
            qs = self.filter_for_tenant(qs, user)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = RentPaymentListSerializer(
                page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = RentPaymentListSerializer(
            qs, many=True, context={'request': request})
        return Response(serializer.data)


@extend_schema(tags=["Payments"])
class PaymentViewSet(BaseViewSet):
    """ViewSet for general payments"""
    queryset = Payment.objects.select_related(
        'tenant', 'invoice', 'transaction', 'receipt')
    serializer_class = PaymentSerializer
    filterset_fields = ['status', 'tenant', 'invoice', 'payment_method']
    search_fields = ['reference_number',
                     'tenant__user__first_name', 'tenant__user__last_name']
    ordering_fields = ['payment_date', 'amount', 'created_at']
    ordering = ['-payment_date']

    def get_permissions(self):
        """
        Override permissions to allow tenants to make payments.
        Tenants can POST to quick_payment, but still read-only for list/retrieve.
        """
        if self.action == 'quick_payment':
            # Allow authenticated users (including tenants) to make payments
            return [IsAuthenticated()]
        return super().get_permissions()

    def filter_for_property_manager(self, queryset, user):
        """Filter payments for property manager's tenants"""
        from tenant.models import Tenant
        managed_tenant_ids = Tenant.objects.filter(
            unit__property__manager=user
        ).values_list('id', flat=True)
        return queryset.filter(tenant_id__in=managed_tenant_ids)

    def filter_for_tenant(self, queryset, user):
        """Filter payments for specific tenant"""
        try:
            tenant = user.tenant_profile
            return queryset.filter(tenant=tenant)
        except:
            return queryset.none()

    def create(self, request, *args, **kwargs):
        """Create a new payment"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()

        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """Process a pending payment"""
        payment = self.get_object()

        try:
            receipt = payment.process(processed_by=request.user)
            return Response({
                'status': 'Payment processed successfully',
                'receipt': ReceiptSerializer(receipt).data
            })
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'], url_path='quick_payment')
    def quick_payment(self, request):
        """
        Create and immediately process a payment.
        
        Auto-generates reference number if not provided.
        Validates invoice ownership and payment amount.
        Tenants can only make payments for themselves.
        """
        serializer = ProcessPaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Extract required fields
        tenant_id = request.data.get('tenant_id')
        invoice_id = request.data.get('invoice_id')
        amount = serializer.validated_data.get('amount')

        if not tenant_id:
            return Response(
                {'error': 'tenant_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from tenant.models import Tenant
            tenant = Tenant.objects.get(id=tenant_id)
            
            # Security: Tenants can only make payments for themselves
            if request.user.role == 'tenant':
                if not hasattr(request.user, 'tenant_profile'):
                    return Response(
                        {'error': 'User does not have a tenant profile'},
                        status=status.HTTP_403_FORBIDDEN
                    )
                if request.user.tenant_profile.id != tenant.id:
                    return Response(
                        {'error': 'You can only make payments for yourself'},
                        status=status.HTTP_403_FORBIDDEN
                    )
            invoice = None
            
            # Validate and fetch invoice if provided
            if invoice_id:
                try:
                    invoice = Invoice.objects.get(id=invoice_id)
                    
                    # Validate invoice belongs to tenant
                    if invoice.tenant_id != tenant.id:
                        return Response(
                            {'error': 'Invoice does not belong to this tenant'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                except Invoice.DoesNotExist:
                    return Response(
                        {'error': 'Invoice not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )

            # If no amount specified and invoice exists, use balance due
            if not amount and invoice:
                amount = invoice.balance_due

            if not amount:
                return Response(
                    {'error': 'amount is required when no invoice specified'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate payment amount
            if amount <= 0:
                return Response(
                    {'error': 'Payment amount must be greater than zero'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate amount doesn't exceed balance (with small tolerance for overpayment)
            if invoice and amount > invoice.balance_due + Decimal('0.01'):
                return Response(
                    {
                        'error': f'Payment amount ({amount}) exceeds invoice balance ({invoice.balance_due})',
                        'balance_due': str(invoice.balance_due)
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create and process payment
            with db_transaction.atomic():
                payment = Payment.objects.create(
                    tenant=tenant,
                    invoice=invoice,
                    amount=amount,
                    payment_method=serializer.validated_data['payment_method'],
                    reference_number=serializer.validated_data.get(
                        'reference_number', ''),  # Will auto-generate if empty
                    notes=serializer.validated_data.get('notes', '')
                )

                receipt = payment.process(processed_by=request.user)

                # Refresh invoice to get updated data
                if invoice:
                    invoice.refresh_from_db()

                return Response({
                    'status': 'success',
                    'message': 'Payment processed successfully',
                    'payment': PaymentSerializer(payment).data,
                    'receipt': ReceiptSerializer(receipt).data,
                    'invoice': InvoiceSerializer(invoice).data if invoice else None
                }, status=status.HTTP_201_CREATED)

        except Tenant.DoesNotExist:
            return Response(
                {'error': 'Tenant not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Payment processing failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(tags=["Dashboard"])
class DashboardViewSet(viewsets.ViewSet):
    """Dashboard analytics endpoints with role-based filtering"""
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Get dashboard overview based on user role"""
        user = request.user
        today = date.today()
        current_month = today.month
        current_year = today.year

        if user.role == 'admin':
            return self._admin_overview(current_month, current_year, today)
        elif user.role == 'property_manager':
            return self._property_manager_overview(user, current_month, current_year, today)
        elif user.role == 'tenant':
            return self._tenant_overview(user, current_month, current_year, today)

        return Response({'error': 'Invalid user role'}, status=status.HTTP_403_FORBIDDEN)

    def _admin_overview(self, current_month, current_year, today):
        """Admin dashboard overview - all data"""
        # Invoice statistics
        total_invoices = Invoice.objects.count()
        draft_invoices = Invoice.objects.filter(status='draft').count()
        sent_invoices = Invoice.objects.filter(status='sent').count()
        overdue_invoices = Invoice.objects.filter(
            due_date__lt=today,
            status__in=['sent', 'partial']
        ).count()
        paid_invoices = Invoice.objects.filter(status='paid').count()

        # Payment statistics
        pending_payments = RentPayment.objects.filter(status='pending').count()
        partial_payments = RentPayment.objects.filter(status='partial').count()

        # Financial totals
        total_outstanding = Invoice.objects.filter(
            status__in=['sent', 'partial']
        ).aggregate(
            total=Sum(F('total_amount') - F('amount_paid'))
        )['total'] or Decimal('0.00')

        monthly_revenue = Transaction.objects.filter(
            transaction_type='payment',
            created_at__month=current_month,
            created_at__year=current_year
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        monthly_charges = Transaction.objects.filter(
            transaction_type='charge',
            created_at__month=current_month,
            created_at__year=current_year
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Account balances
        total_debt = UserAccount.objects.filter(
            balance__lt=0
        ).aggregate(
            total=Sum('balance')
        )['total'] or Decimal('0.00')

        accounts_in_debt = UserAccount.objects.filter(balance__lt=0).count()

        # Billing periods - Fixed to handle multiple active periods
        try:
            current_period = BillingPeriod.objects.filter(
                start_date__lte=today,
                end_date__gte=today,
                is_active=True
            ).order_by('-start_date').first()

            current_period_name = current_period.name if current_period else None
            days_until_due = current_period.days_until_due if current_period else None
        except Exception:
            current_period_name = None
            days_until_due = None

        # Collection rate
        total_billed = monthly_charges + total_outstanding
        collection_rate = (
            (monthly_revenue / total_billed * 100)
            if total_billed > 0 else 0
        )

        return Response({
            'total_invoices': total_invoices,
            'draft_invoices': draft_invoices,
            'sent_invoices': sent_invoices,
            'overdue_invoices': overdue_invoices,
            'paid_invoices': paid_invoices,
            'pending_payments': pending_payments,
            'partial_payments': partial_payments,
            'total_outstanding': float(total_outstanding),
            'monthly_revenue': float(monthly_revenue),
            'monthly_charges': float(monthly_charges),
            'total_debt': float(abs(total_debt)),
            'accounts_in_debt': accounts_in_debt,
            'collection_rate': round(float(collection_rate), 2),
            'current_period': current_period_name,
            'days_until_due': days_until_due
        })

    def _property_manager_overview(self, user, current_month, current_year, today):
        """Property manager dashboard - only their properties"""
        from tenant.models import Tenant

        # Get tenants managed by this property manager
        managed_tenants = Tenant.objects.filter(
            unit__property__manager=user,
            status=Tenant.TenantStatus.ACTIVE
        )

        tenant_ids = managed_tenants.values_list('id', flat=True)

        # Invoice statistics for managed properties
        invoices = Invoice.objects.filter(tenant_id__in=tenant_ids)
        total_invoices = invoices.count()
        draft_invoices = invoices.filter(status='draft').count()
        sent_invoices = invoices.filter(status='sent').count()
        overdue_invoices = invoices.filter(
            due_date__lt=today,
            status__in=['sent', 'partial']
        ).count()
        paid_invoices = invoices.filter(status='paid').count()

        # Payment statistics
        rent_payments = RentPayment.objects.filter(tenant_id__in=tenant_ids)
        pending_payments = rent_payments.filter(status='pending').count()
        partial_payments = rent_payments.filter(status='partial').count()

        # Financial totals
        total_outstanding = invoices.filter(
            status__in=['sent', 'partial']
        ).aggregate(
            total=Sum(F('total_amount') - F('amount_paid'))
        )['total'] or Decimal('0.00')

        # Get accounts for managed tenants
        account_ids = managed_tenants.values_list(
            'user__account__id', flat=True)

        monthly_revenue = Transaction.objects.filter(
            account_id__in=account_ids,
            transaction_type='payment',
            created_at__month=current_month,
            created_at__year=current_year
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        monthly_charges = Transaction.objects.filter(
            account_id__in=account_ids,
            transaction_type='charge',
            created_at__month=current_month,
            created_at__year=current_year
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Account balances
        total_debt = UserAccount.objects.filter(
            id__in=account_ids,
            balance__lt=0
        ).aggregate(
            total=Sum('balance')
        )['total'] or Decimal('0.00')

        accounts_in_debt = UserAccount.objects.filter(
            id__in=account_ids,
            balance__lt=0
        ).count()

        # Properties and units
        from property.models import Property, Unit
        properties = Property.objects.filter(manager=user)
        total_properties = properties.count()
        total_units = Unit.objects.filter(
            property__manager=user
        ).count()
        occupied_units = managed_tenants.count()
        occupancy_rate = (occupied_units / total_units *
                          100) if total_units > 0 else 0

        # Billing periods - Fixed to handle multiple active periods
        try:
            current_period = BillingPeriod.objects.filter(
                start_date__lte=today,
                end_date__gte=today,
                is_active=True
            ).order_by('-start_date').first()

            current_period_name = current_period.name if current_period else None
            days_until_due = current_period.days_until_due if current_period else None
        except Exception:
            current_period_name = None
            days_until_due = None

        # Collection rate
        total_billed = monthly_charges + total_outstanding
        collection_rate = (
            (monthly_revenue / total_billed * 100)
            if total_billed > 0 else 0
        )

        return Response({
            'role': 'property_manager',
            'total_properties': total_properties,
            'total_units': total_units,
            'occupied_units': occupied_units,
            'occupancy_rate': round(float(occupancy_rate), 1),
            'total_invoices': total_invoices,
            'draft_invoices': draft_invoices,
            'sent_invoices': sent_invoices,
            'overdue_invoices': overdue_invoices,
            'paid_invoices': paid_invoices,
            'pending_payments': pending_payments,
            'partial_payments': partial_payments,
            'total_outstanding': float(total_outstanding),
            'monthly_revenue': float(monthly_revenue),
            'monthly_charges': float(monthly_charges),
            'total_debt': float(abs(total_debt)),
            'accounts_in_debt': accounts_in_debt,
            'collection_rate': round(float(collection_rate), 2),
            'current_period': current_period_name,
            'days_until_due': days_until_due
        })

    def _tenant_overview(self, user, current_month, current_year, today):
        """Tenant dashboard - only their own data"""
        try:
            tenant = user.tenant_profile
        except:
            return Response(
                {'error': 'Tenant profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get tenant's invoices
        invoices = Invoice.objects.filter(tenant=tenant)
        total_invoices = invoices.count()
        overdue_invoices = invoices.filter(
            due_date__lt=today,
            status__in=['sent', 'partial']
        ).count()
        paid_invoices = invoices.filter(status='paid').count()

        # Current balance
        account = user.account
        current_balance = account.balance
        is_in_debt = account.is_in_debt
        debt_amount = account.debt_amount

        # Next payment
        next_payment = RentPayment.objects.filter(
            tenant=tenant,
            status='pending',
            due_date__gte=today
        ).order_by('due_date').first()

        next_payment_date = next_payment.due_date if next_payment else None
        next_payment_amount = next_payment.amount if next_payment else None
        days_until_payment = (next_payment_date -
                              today).days if next_payment_date else None

        # Lease info
        lease_end_date = tenant.lease_end_date if hasattr(
            tenant, 'lease_end_date') else None
        lease_status = tenant.status

        # Monthly payments this year
        monthly_payments = Transaction.objects.filter(
            account=account,
            transaction_type='payment',
            created_at__year=current_year
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Billing period - Fixed to handle multiple active periods
        try:
            current_period = BillingPeriod.objects.filter(
                start_date__lte=today,
                end_date__gte=today,
                is_active=True
            ).order_by('-start_date').first()

            current_period_name = current_period.name if current_period else None
        except Exception:
            current_period_name = None

        return Response({
            'role': 'tenant',
            'current_balance': float(current_balance),
            'is_in_debt': is_in_debt,
            'debt_amount': float(debt_amount),
            'total_invoices': total_invoices,
            'overdue_invoices': overdue_invoices,
            'paid_invoices': paid_invoices,
            'next_payment_date': str(next_payment_date) if next_payment_date else None,
            'next_payment_amount': float(next_payment_amount) if next_payment_amount else None,
            'days_until_payment': days_until_payment,
            'lease_status': lease_status,
            'lease_end_date': str(lease_end_date) if lease_end_date else None,
            'monthly_rent': float(tenant.monthly_rent) if hasattr(tenant, 'monthly_rent') else None,
            'property_address': tenant.unit.property.address,
            'unit_number': tenant.unit.unit_number if hasattr(tenant, 'unit') else None,
            'yearly_payments': float(monthly_payments),
            'current_period': current_period_name,
        })

    @action(detail=False, methods=['get'])
    def recent_activity(self, request):
        """Get recent activity based on user role"""
        user = request.user
        limit = int(request.query_params.get('limit', 20))

        if user.role == 'admin':
            return self._admin_recent_activity(limit)
        elif user.role == 'property_manager':
            return self._property_manager_recent_activity(user, limit)
        elif user.role == 'tenant':
            return self._tenant_recent_activity(user, limit)

        return Response({'error': 'Invalid user role'}, status=status.HTTP_403_FORBIDDEN)

    def _admin_recent_activity(self, limit):
        """Recent activity for admin - all data"""
        recent_transactions = Transaction.objects.select_related(
            'account', 'invoice'
        ).order_by('-created_at')[:limit]

        recent_payments = Payment.objects.select_related(
            'tenant', 'invoice'
        ).order_by('-created_at')[:limit]

        recent_receipts = Receipt.objects.select_related(
            'tenant', 'invoice'
        ).order_by('-created_at')[:limit]

        recent_invoices = Invoice.objects.select_related(
            'tenant', 'billing_period'
        ).order_by('-created_at')[:limit]

        return Response({
            'transactions': TransactionListSerializer(
                recent_transactions, many=True, context={'request': self.request}
            ).data,
            'payments': PaymentSerializer(
                recent_payments, many=True, context={'request': self.request}
            ).data,
            'receipts': ReceiptSerializer(
                recent_receipts, many=True, context={'request': self.request}
            ).data,
            'invoices': InvoiceListSerializer(
                recent_invoices, many=True, context={'request': self.request}
            ).data
        })

    def _property_manager_recent_activity(self, user, limit):
        """Recent activity for property manager"""
        from tenant.models import Tenant

        managed_tenants = Tenant.objects.filter(
            unit__property__manager=user,
            status=Tenant.TenantStatus.ACTIVE
        )

        tenant_ids = managed_tenants.values_list('id', flat=True)
        account_ids = managed_tenants.values_list(
            'user__account__id', flat=True)

        recent_transactions = Transaction.objects.filter(
            account_id__in=account_ids
        ).select_related('account', 'invoice').order_by('-created_at')[:limit]

        recent_payments = Payment.objects.filter(
            tenant_id__in=tenant_ids
        ).select_related('tenant', 'invoice').order_by('-created_at')[:limit]

        recent_receipts = Receipt.objects.filter(
            tenant_id__in=tenant_ids
        ).select_related('tenant', 'invoice').order_by('-created_at')[:limit]

        recent_invoices = Invoice.objects.filter(
            tenant_id__in=tenant_ids
        ).select_related('tenant', 'billing_period').order_by('-created_at')[:limit]

        return Response({
            'transactions': TransactionListSerializer(
                recent_transactions, many=True, context={'request': self.request}
            ).data,
            'payments': PaymentSerializer(
                recent_payments, many=True, context={'request': self.request}
            ).data,
            'receipts': ReceiptSerializer(
                recent_receipts, many=True, context={'request': self.request}
            ).data,
            'invoices': InvoiceListSerializer(
                recent_invoices, many=True, context={'request': self.request}
            ).data
        })

    def _tenant_recent_activity(self, user, limit):
        """Recent activity for tenant"""
        try:
            tenant = user.tenant_profile
        except:
            return Response(
                {'error': 'Tenant profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        account = user.account

        recent_transactions = Transaction.objects.filter(
            account=account
        ).select_related('account', 'invoice').order_by('-created_at')[:limit]

        recent_payments = Payment.objects.filter(
            tenant=tenant
        ).select_related('tenant', 'invoice').order_by('-created_at')[:limit]

        recent_receipts = Receipt.objects.filter(
            tenant=tenant
        ).select_related('tenant', 'invoice').order_by('-created_at')[:limit]

        recent_invoices = Invoice.objects.filter(
            tenant=tenant
        ).select_related('tenant', 'billing_period').order_by('-created_at')[:limit]

        return Response({
            'transactions': TransactionListSerializer(
                recent_transactions, many=True, context={'request': self.request}
            ).data,
            'payments': PaymentSerializer(
                recent_payments, many=True, context={'request': self.request}
            ).data,
            'receipts': ReceiptSerializer(
                recent_receipts, many=True, context={'request': self.request}
            ).data,
            'invoices': InvoiceListSerializer(
                recent_invoices, many=True, context={'request': self.request}
            ).data
        })


@extend_schema(tags=["Reports"])
class TenantStatementViewSet(viewsets.ViewSet):
    """ViewSet for tenant statements and account ledgers"""
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def generate(self, request):
        """Generate tenant statement for a period"""
        tenant_id = request.query_params.get('tenant_id')
        period_start = request.query_params.get('period_start')
        period_end = request.query_params.get('period_end')

        if not all([tenant_id, period_start, period_end]):
            return Response(
                {'error': 'tenant_id, period_start, and period_end are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from tenant.models import Tenant
            from datetime import datetime

            tenant = Tenant.objects.get(id=tenant_id)
            start_date = datetime.strptime(period_start, '%Y-%m-%d').date()
            end_date = datetime.strptime(period_end, '%Y-%m-%d').date()

            # Get opening balance (balance before period start)
            opening_transactions = Transaction.objects.filter(
                account=tenant.user.account,
                created_at__date__lt=start_date
            )

            opening_balance = Decimal('0.00')
            for trans in opening_transactions:
                if trans.transaction_type in ['payment', 'refund', 'credit']:
                    opening_balance += trans.amount
                else:
                    opening_balance -= trans.amount

            # Get transactions in period
            transactions = Transaction.objects.filter(
                account=tenant.user.account,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date
            ).order_by('created_at')

            # Get invoices in period
            invoices = Invoice.objects.filter(
                tenant=tenant,
                issue_date__gte=start_date,
                issue_date__lte=end_date
            ).order_by('issue_date')

            # Get receipts in period
            receipts = Receipt.objects.filter(
                tenant=tenant,
                payment_date__gte=start_date,
                payment_date__lte=end_date
            ).order_by('payment_date')

            # Calculate totals
            total_charges = transactions.filter(
                transaction_type__in=['charge', 'penalty']
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

            total_payments = transactions.filter(
                transaction_type__in=['payment', 'refund', 'credit']
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

            closing_balance = opening_balance + total_payments - total_charges

            statement_data = {
                'tenant_id': tenant.id,
                'tenant_name': tenant.user.get_full_name(),
                'period_start': start_date,
                'period_end': end_date,
                'opening_balance': opening_balance,
                'closing_balance': closing_balance,
                'total_charges': total_charges,
                'total_payments': total_payments,
                'transactions': transactions,
                'invoices': invoices,
                'receipts': receipts
            }

            serializer = TenantStatementSerializer(statement_data)
            return Response(serializer.data)

        except Tenant.DoesNotExist:
            return Response(
                {'error': 'Tenant not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            return Response(
                {'error': f'Invalid date format. Use YYYY-MM-DD: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def current_balance(self, request):
        """Get current balance for a tenant"""
        tenant_id = request.query_params.get('tenant_id')

        if not tenant_id:
            return Response(
                {'error': 'tenant_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from tenant.models import Tenant
            tenant = Tenant.objects.get(id=tenant_id)
            account = tenant.user.account

            return Response({
                'tenant_id': tenant.id,
                'tenant_name': tenant.user.get_full_name(),
                'current_balance': account.balance,
                'debt_amount': account.debt_amount,
                'is_in_debt': account.is_in_debt,
                'available_credit': account.available_credit,
                'credit_limit': account.credit_limit
            })

        except Tenant.DoesNotExist:
            return Response(
                {'error': 'Tenant not found'},
                status=status.HTTP_404_NOT_FOUND
            )
