from finance.routers.accounts import router as accounts_router

from finance.routers.billing import router as billing_router
from finance.routers.invoices import router as invoices_router
from finance.routers.dashboard import router as dashboard_router

urlpatterns = (
    accounts_router.urls +
    billing_router.urls +
    invoices_router.urls +
    dashboard_router.urls
)
