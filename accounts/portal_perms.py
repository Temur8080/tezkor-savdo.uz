"""Portal huquqlari — smartbozor2 usuli: faqat Django user_permissions / groups.

O‘ng ustun (Tanlangan) = berilgan → ko‘rinadi / ishlaydi.
Chap ustun (Mavjud) = berilmagan → ko‘rinmaydi.
"""

from __future__ import annotations

ROLE_SALES = 'Sales Agent'
ROLE_CONSULTANT = 'Consultant'
ROLE_MANAGER = 'Manager'

# Django Permission.codename → label
PORTAL_PERMISSIONS = (
    ('portal_multi_branch', 'Ko‘p filial / menejer ko‘rinishi'),
    ('portal_dashboard', 'Boshqaruv'),
    ('portal_pos', 'Kassa'),
    ('portal_sales', 'Sotuvlar'),
    ('portal_inventory', 'Ombor'),
    ('portal_reports', 'Hisobotlar'),
    ('portal_customers', 'Mijozlar'),
    ('portal_inventory_intake', 'Ombor kirimi'),
    ('portal_employees', 'Xodimlar'),
    ('portal_warranty', 'Kafolat'),
    ('portal_returns', 'Qaytarishlar'),
    ('portal_debtors', 'Qarzdorlar'),
    ('portal_reservations', 'Bronlar'),
    ('portal_expenses', 'Xarajatlar'),
    ('portal_audit', 'Audit'),
    ('portal_settings', 'Sozlamalar'),
    ('portal_sale_complete', 'Sotuvni yakunlash'),
    ('portal_return_process', 'Qaytarishni amalga oshirish'),
)

PORTAL_CODENAMES = frozenset(code for code, _ in PORTAL_PERMISSIONS)
PORTAL_PERM_LABELS = dict(PORTAL_PERMISSIONS)

# Qisqa kod (navbar/decorator) → Permission.codename
CAP_TO_PERM = {
    'multi_branch': 'portal_multi_branch',
    'dashboard': 'portal_dashboard',
    'pos': 'portal_pos',
    'sales': 'portal_sales',
    'inventory': 'portal_inventory',
    'reports': 'portal_reports',
    'customers': 'portal_customers',
    'inventory_intake': 'portal_inventory_intake',
    'employees': 'portal_employees',
    'warranty': 'portal_warranty',
    'returns': 'portal_returns',
    'debtors': 'portal_debtors',
    'reservations': 'portal_reservations',
    'expenses': 'portal_expenses',
    'audit': 'portal_audit',
    'settings': 'portal_settings',
    'sale_complete': 'portal_sale_complete',
    'return_process': 'portal_return_process',
}

PERM_TO_CAP = {v: k for k, v in CAP_TO_PERM.items()}

ROLE_DEFAULT_CAPS = {
    ROLE_MANAGER: frozenset(CAP_TO_PERM.keys()),
    ROLE_SALES: frozenset({
        'pos', 'sales', 'inventory', 'inventory_intake', 'returns',
        'sale_complete', 'return_process', 'reservations', 'debtors',
    }),
    ROLE_CONSULTANT: frozenset({'pos', 'sales', 'reservations'}),
}


def perm_full_name(codename: str) -> str:
    return f'accounts.{codename}'


def role_default_codenames(role: str) -> frozenset[str]:
    caps = ROLE_DEFAULT_CAPS.get(role, frozenset())
    return frozenset(CAP_TO_PERM[c] for c in caps if c in CAP_TO_PERM)


def get_portal_permission_qs():
    from django.contrib.auth.models import Permission
    return Permission.objects.filter(
        content_type__app_label='accounts',
        codename__in=PORTAL_CODENAMES,
    ).select_related('content_type')


def assign_role_permissions(user, role: str, *, replace: bool = True) -> None:
    """Yangi xodim / rol seed: lavozim default huquqlarini user_permissions ga yozadi."""
    from django.contrib.auth.models import Permission

    wanted = role_default_codenames(role)
    perms = Permission.objects.filter(
        content_type__app_label='accounts',
        codename__in=wanted,
    )
    if replace:
        # Faqat portal huquqlarini almashtirish; boshqa Django perms saqlanadi
        portal = list(get_portal_permission_qs())
        if portal:
            user.user_permissions.remove(*portal)
        if perms:
            user.user_permissions.add(*perms)
    else:
        if perms:
            user.user_permissions.add(*perms)
    for attr in ('_perm_cache', '_user_perm_cache', '_group_perm_cache'):
        if hasattr(user, attr):
            delattr(user, attr)


def get_portal_caps(user) -> frozenset[str]:
    """Berilgan portal huquqlari (qisqa kodlar). Superuser — hammasi."""
    if not user or not getattr(user, 'is_authenticated', False):
        return frozenset()
    if user.is_superuser:
        return frozenset(CAP_TO_PERM.keys())

    caps = set()
    for codename in PORTAL_CODENAMES:
        if user.has_perm(perm_full_name(codename)):
            cap = PERM_TO_CAP.get(codename)
            if cap:
                caps.add(cap)
    return frozenset(caps)


def has_portal_cap(user, code: str) -> bool:
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return code in CAP_TO_PERM
    codename = CAP_TO_PERM.get(code)
    if not codename:
        return False
    return user.has_perm(perm_full_name(codename))
