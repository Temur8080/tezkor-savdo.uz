\
\
\
\
\
\
\
\
\
\
\
\
\
\
\

from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static

admin.site.site_header = "Tezkor boshqaruvi (faqat superuser)"
admin.site.site_title = "Tezkor POS"
admin.site.index_title = "Boshqaruv paneli"

def _admin_superuser_only(request):
    return bool(
        getattr(request, 'user', None)
        and request.user.is_active
        and request.user.is_superuser
    )

admin.site.has_permission = _admin_superuser_only

urlpatterns = [
    path('admin/', admin.site.urls),

    path('pos_terminal/api/', include('accounts.urls')),
    path('', include('accounts.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
