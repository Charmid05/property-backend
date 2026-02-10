from rest_framework.routers import DefaultRouter
from finance.views import InvoiceViewSet, InvoiceItemViewSet, PaymentViewSet, ReceiptViewSet, TenantStatementViewSet, TransactionViewSet, RentPaymentViewSet

router = DefaultRouter()
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'invoice-items', InvoiceItemViewSet, basename='invoiceitem')
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'rent-payments', RentPaymentViewSet, basename='rentpayment')
router.register(r'receipts', ReceiptViewSet, basename='receipt')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'statements', TenantStatementViewSet, basename='statement')