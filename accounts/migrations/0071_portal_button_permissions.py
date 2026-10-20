from django.db import migrations


PERM_DEFS = (
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

BTN_CODES = [c for c, _ in PERM_DEFS if c.startswith('portal_btn_')]


def apply_perms(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Employee = apps.get_model('accounts', 'Employee')
    User = apps.get_model('auth', 'User')

    ct, _ = ContentType.objects.get_or_create(app_label='accounts', model='portalfeature')
    portal = {}
    for code, name in PERM_DEFS:
        p, _ = Permission.objects.get_or_create(
            content_type=ct, codename=code, defaults={'name': name},
        )
        if p.name != name:
            p.name = name
            p.save(update_fields=['name'])
        portal[code] = p

    through = User.user_permissions.through
    btn_ids = [portal[c].id for c in BTN_CODES if c in portal]

    # Menejerlarga barcha yangi tugma huquqlarini qo‘shish
    for emp in Employee.objects.filter(role='Manager', is_active=True).iterator():
        existing = set(
            through.objects.filter(user_id=emp.user_id, permission_id__in=btn_ids)
            .values_list('permission_id', flat=True)
        )
        to_add = [
            through(user_id=emp.user_id, permission_id=pid)
            for pid in btn_ids if pid not in existing
        ]
        if to_add:
            through.objects.bulk_create(to_add, ignore_conflicts=True)

    # Sotuvchilarga asosiy tugmalar
    sales_btns = [
        'portal_btn_export', 'portal_btn_sale_edit', 'portal_btn_product_edit',
        'portal_btn_debt_pay', 'portal_btn_reservation_cancel',
    ]
    sales_ids = [portal[c].id for c in sales_btns if c in portal]
    for emp in Employee.objects.filter(role='Sales Agent', is_active=True).iterator():
        existing = set(
            through.objects.filter(user_id=emp.user_id, permission_id__in=sales_ids)
            .values_list('permission_id', flat=True)
        )
        to_add = [
            through(user_id=emp.user_id, permission_id=pid)
            for pid in sales_ids if pid not in existing
        ]
        if to_add:
            through.objects.bulk_create(to_add, ignore_conflicts=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0070_smartbozor_portal_permissions'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='portalfeature',
            options={
                'default_permissions': (),
                'permissions': PERM_DEFS,
                'verbose_name': 'Portal huquqi',
                'verbose_name_plural': 'Portal huquqlari',
            },
        ),
        migrations.RunPython(apply_perms, noop),
    ]
