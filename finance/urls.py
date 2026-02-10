from django.urls import path, include
from .routers import urlpatterns as finance_urls

urlpatterns = [
    path('finance/', include(finance_urls)),
]
