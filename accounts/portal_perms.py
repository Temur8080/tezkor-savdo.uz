"""Portal huquqlari: rol → default to‘plam; StaffAccess orqali qo‘shish/olib tashlash."""

from __future__ import annotations

ROLE_SALES = 'Sales Agent'
ROLE_CONSULTANT = 'Consultant'
ROLE_MANAGER = 'Manager'

# code → label (admin + UI)
PORTAL_CAPABILITIES = (
    ('multi_branch', 'Ko‘p filial / menejer ko‘rinishi'),
    ('dashboard', 'Boshqaruv'),
    ('pos', 'Kassa'),
    ('sales', 'Sotuvlar'),
    ('inventory', 'Ombor'),
    ('reports', 'Hisobotlar'),
    ('customers', 'Mijozlar'),
    ('inventory_intake', 'Ombor kirimi'),
    ('employees', 'Xodimlar'),
    ('warranty', 'Kafolat'),
    ('returns', 'Qaytarishlar'),
    ('debtors', 'Qarzdorlar'),
    ('reservations', 'Bronlar'),
    ('expenses', 'Xarajatlar'),
    ('audit', 'Audit'),
    ('settings', 'Sozlamalar'),
    ('sale_complete', 'Sotuvni yakunlash'),
    ('return_process', 'Qaytarishni amalga oshirish'),
)

PORTAL_CAP_CODES = frozenset(code for code, _ in PORTAL_CAPABILITIES)
PORTAL_CAP_LABELS = dict(PORTAL_CAPABILITIES)

_ALL = frozenset(PORTAL_CAP_CODES)

ROLE_DEFAULT_CAPS = {
    ROLE_MANAGER: _ALL,
    ROLE_SALES: frozenset({
        'pos',
        'sales',
        'inventory',
        'inventory_intake',
        'returns',
        'sale_complete',
        'return_process',
        'reservations',
        'debtors',
    }),
    ROLE_CONSULTANT: frozenset({
        'pos',
        'sales',
        'reservations',
    }),
}


def role_default_caps(role: str) -> frozenset[str]:
    return ROLE_DEFAULT_CAPS.get(role, frozenset())


def get_portal_caps(user) -> frozenset[str]:
    """Effective portal huquqlari: (rol ∪ qo‘shimcha) − olib tashlangan."""
    if not user or not getattr(user, 'is_authenticated', False):
        return frozenset()
    if user.is_superuser:
        return _ALL

    from accounts.models import Employee

    emp = (
        Employee.objects
        .filter(user=user, is_active=True)
        .only('role')
        .first()
    )
    if emp is None:
        return frozenset()

    caps = set(role_default_caps(emp.role))
    access = getattr(user, 'staff_access', None)
    if access is not None:
        try:
            caps.update(access.extra_capabilities.values_list('code', flat=True))
            caps.difference_update(access.denied_capabilities.values_list('code', flat=True))
        except Exception:
            pass
    return frozenset(c for c in caps if c in PORTAL_CAP_CODES)


def has_portal_cap(user, code: str) -> bool:
    if code not in PORTAL_CAP_CODES:
        return False
    return code in get_portal_caps(user)
