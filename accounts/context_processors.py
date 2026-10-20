from django.conf import settings

from .models import AppSettings, Organization
from .portal_perms import get_portal_caps


def branding(request):

    org = None
    try:
        if (
            getattr(request, 'user', None)
            and request.user.is_authenticated
            and hasattr(request.user, 'employee')
            and request.user.employee
            and request.user.employee.branch_id
        ):
            branch = request.user.employee.branch
            org = branch.organization or Organization.get_default()
    except Exception:
        org = None

    if org is None:
        try:
            org = Organization.get_default()
        except Exception:
            org = None

    brand_name = getattr(org, 'brand_name', None) or getattr(settings, 'COMPANY_BRAND', 'Tezkor')
    company_name = getattr(org, 'name', None) or getattr(settings, 'COMPANY_NAME', 'Tezkor Savdo')
    logo_url = None
    if org and org.logo:
        try:
            logo_url = org.logo.url
        except Exception:
            logo_url = None
    if not logo_url:
        logo_url = getattr(settings, 'COMPANY_LOGO_STATIC', 'images/tezkor-logo.jpg')

    theme = {
        'mode': 'system',
        'day_start': 6,
        'night_start': 19,
    }
    try:
        app = AppSettings.get_solo()
        theme = {
            'mode': app.theme_mode or 'system',
            'day_start': int(app.theme_day_start if app.theme_day_start is not None else 6),
            'night_start': int(app.theme_night_start if app.theme_night_start is not None else 19),
        }
    except Exception:
        pass

    portal_caps = frozenset()
    try:
        if getattr(request, 'user', None) and request.user.is_authenticated:
            portal_caps = get_portal_caps(request.user)
    except Exception:
        portal_caps = frozenset()

    return {
        'brand': {
            'brand_name': brand_name,
            'company_name': company_name,
            'logo_url': logo_url,
            'logo_is_static': not (org and org.logo),
            'organization': org,
        },
        'theme_settings': theme,
        'portal_caps': portal_caps,
    }
