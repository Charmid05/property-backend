
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf.urls.static import static
from django.conf import settings

from rest_framework import permissions
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from a_users.views import *


urlpatterns = [
    path('admin/', admin.site.urls),
    # path('home/', include('home.urls')),
    path('api/auth/', include('a_users.urls')),
    path('api/', include('tenant.urls')),
    path('api/', include('property.urls')),
    path('api/', include('finance.urls')),
    path('api/', include('management.urls')),
    path('api/', include('maintenance.urls')),
    # JWT Token endpoints
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'),
         name='swagger-ui'),
    path('api/docs/redoc/',
         SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    path('silk/', include('silk.urls', namespace='silk')),
]
# Only used when DEBUG=True, whitenoise can serve files when DEBUG=False
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
