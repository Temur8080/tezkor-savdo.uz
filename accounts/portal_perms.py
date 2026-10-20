"""Portal huquqlari — smartbozor2 usuli: Django user_permissions.

O‘ng = berilgan (ko‘rinadi/ishlaydi). Chap = berilmagan (ko‘rinmaydi).
"""

from __future__ import annotations

ROLE_SALES = 'Sales Agent'
ROLE_CONSULTANT = 'Consultant'
ROLE_MANAGER = 'Manager'

# Django Permission.codename → admin label
PORTAL_PERMISSIONS = (
    # Menyu / sahifa
    ('portal_multi_branch', 'Menyu: Ko‘p filial ko‘rinishi'),
    ('portal_dashboard', 'Menyu: Boshqaruv'),
    ('portal_pos', 'Menyu: Kassa'),
    ('portal_sales', 'Menyu: Sotuvlar'),
    ('portal_inventory', 'Menyu: Ombor'),
    ('portal_reports', 'Menyu: Hisobotlar'),
    ('portal_customers', 'Menyu: Mijozlar'),
    ('portal_inventory_intake', 'Menyu: Ombor kirimi'),
    ('portal_employees', 'Menyu: Xodimlar'),
    ('portal_warranty', 'Menyu: Kafolat'),
    ('portal_returns', 'Menyu: Qaytarishlar'),
    ('portal_debtors', 'Menyu: Qarzdorlar'),
    ('portal_reservations', 'Menyu: Bronlar'),
    ('portal_expenses', 'Menyu: Xarajatlar'),
    ('portal_audit', 'Menyu: Audit'),
    ('portal_settings', 'Menyu: Sozlamalar'),
    ('portal_sale_complete', 'Amal: Sotuvni yakunlash'),
    ('portal_return_process', 'Amal: Qaytarishni bajarish'),
    # Tugmalar
    ('portal_btn_export', 'Tugma: CSV eksport'),
    ('portal_btn_sale_edit', 'Tugma: Sotuvni tahrirlash'),
    ('portal_btn_sale_delete', 'Tugma: Sotuvni o‘chirish'),
    ('portal_btn_order_approve', 'Tugma: Buyurtmani tasdiqlash / bekor'),
    ('portal_btn_product_edit', 'Tugma: Mahsulotni tahrirlash'),
    ('portal_btn_product_delete', 'Tugma: Mahsulotni o‘chirish'),
    ('portal_btn_employee_add', 'Tugma: Xodim qo‘shish'),
    ('portal_btn_employee_edit', 'Tugma: Xodimni tahrirlash'),
    ('portal_btn_employee_block', 'Tugma: Xodimni bloklash'),
    ('portal_btn_employee_delete', 'Tugma: Xodimni o‘chirish'),
    ('portal_btn_debt_pay', 'Tugma: Qarz to‘lovi'),
    ('portal_btn_debt_edit', 'Tugma: Qarzni tahrirlash'),
    ('portal_btn_debt_delete', 'Tugma: Qarzni o‘chirish'),
    ('portal_btn_expense_add', 'Tugma: Xarajat qo‘shish'),
    ('portal_btn_expense_delete', 'Tugma: Xarajatni o‘chirish'),
    ('portal_btn_customer_edit', 'Tugma: Mijozni tahrirlash'),
    ('portal_btn_customer_delete', 'Tugma: Mijozni o‘chirish'),
    ('portal_btn_reservation_cancel', 'Tugma: Bronni bekor qilish'),
)

PORTAL_CODENAMES = frozenset(code for code, _ in PORTAL_PERMISSIONS)
PORTAL_PERM_LABELS = dict(PORTAL_PERMISSIONS)

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
    'btn_export': 'portal_btn_export',
    'btn_sale_edit': 'portal_btn_sale_edit',
    'btn_sale_delete': 'portal_btn_sale_delete',
    'btn_order_approve': 'portal_btn_order_approve',
    'btn_product_edit': 'portal_btn_product_edit',
    'btn_product_delete': 'portal_btn_product_delete',
    'btn_employee_add': 'portal_btn_employee_add',
    'btn_employee_edit': 'portal_btn_employee_edit',
    'btn_employee_block': 'portal_btn_employee_block',
    'btn_employee_delete': 'portal_btn_employee_delete',
    'btn_debt_pay': 'portal_btn_debt_pay',
    'btn_debt_edit': 'portal_btn_debt_edit',
    'btn_debt_delete': 'portal_btn_debt_delete',
    'btn_expense_add': 'portal_btn_expense_add',
    'btn_expense_delete': 'portal_btn_expense_delete',
    'btn_customer_edit': 'portal_btn_customer_edit',
    'btn_customer_delete': 'portal_btn_customer_delete',
    'btn_reservation_cancel': 'portal_btn_reservation_cancel',
}

PERM_TO_CAP = {v: k for k, v in CAP_TO_PERM.items()}

_MENU_CAPS = frozenset({
    'multi_branch', 'dashboard', 'pos', 'sales', 'inventory', 'reports',
    'customers', 'inventory_intake', 'employees', 'warranty', 'returns',
    'debtors', 'reservations', 'expenses', 'audit', 'settings',
    'sale_complete', 'return_process',
})
_BTN_CAPS = frozenset(c for c in CAP_TO_PERM if c.startswith('btn_'))

ROLE_DEFAULT_CAPS = {
    ROLE_MANAGER: frozenset(CAP_TO_PERM.keys()),
    ROLE_SALES: frozenset({
        'pos', 'sales', 'inventory', 'inventory_intake', 'returns',
        'sale_complete', 'return_process', 'reservations', 'debtors',
        'btn_export', 'btn_sale_edit', 'btn_product_edit',
        'btn_debt_pay', 'btn_reservation_cancel',
    }),
    ROLE_CONSULTANT: frozenset({
        'pos', 'sales', 'reservations',
    }),
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
    from django.contrib.auth.models import Permission

    wanted = role_default_codenames(role)
    perms = Permission.objects.filter(
        content_type__app_label='accounts',
        codename__in=wanted,
    )
    if replace:
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
