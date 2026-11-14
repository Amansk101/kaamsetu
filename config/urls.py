"""Root URL configuration for KaamSetu."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('accounts/', include('accounts.urls')),
    path('worker/', include('workers.urls')),
    path('employer/', include('employers.urls')),
    path('jobs/', include('jobs.urls')),
    path('hiring/', include('hiring.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Custom error pages (rendered by core.views, templates in templates/*.html).
handler400 = 'core.views.bad_request'
handler403 = 'core.views.permission_denied'
handler404 = 'core.views.not_found'
handler500 = 'core.views.server_error'
