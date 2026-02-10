from rest_framework.routers import DefaultRouter
from finance.views import BillingPeriodViewSet, ChargeTypeViewSet, UtilityChargeViewSet

router = DefaultRouter()
router.register(r'billing-periods', BillingPeriodViewSet, basename='billingperiod')
router.register(r'charge-types', ChargeTypeViewSet, basename='chargetype')
router.register(r'utility-charges', UtilityChargeViewSet, basename='utilitycharge')
