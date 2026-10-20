from django.db import migrations, models


def seed_portal_perms_from_roles(apps, schema_editor):
    """Permission yozuvlarini yaratish + lavozim bo‘yicha biriktirish."""
    Employee = apps.get_model('accounts', 'Employee')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    User = apps.get_model('auth', 'User')

    ct, _ = ContentType.objects.get_or_create(app_label='accounts', model='portalfeature')
    perm_defs = (
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
    portal_perms = {}
    for code, name in perm_defs:
        p, _ = Permission.objects.get_or_create(
            content_type=ct,
            codename=code,
            defaults={'name': name},
        )
        if p.name != name:
            p.name = name
            p.save(update_fields=['name'])
        portal_perms[code] = p

    role_map = {
        'Manager': list(portal_perms.keys()),
        'Sales Agent': [
            'portal_pos', 'portal_sales', 'portal_inventory', 'portal_inventory_intake',
            'portal_returns', 'portal_sale_complete', 'portal_return_process',
            'portal_reservations', 'portal_debtors',
        ],
        'Consultant': [
            'portal_pos', 'portal_sales', 'portal_reservations',
        ],
    }

    through = User.user_permissions.through
    all_portal_ids = [p.id for p in portal_perms.values()]

    for emp in Employee.objects.filter(is_active=True).iterator():
        codes = role_map.get(emp.role) or []
        wanted_ids = [portal_perms[c].id for c in codes if c in portal_perms]
        through.objects.filter(user_id=emp.user_id, permission_id__in=all_portal_ids).delete()
        if wanted_ids:
            through.objects.bulk_create([
                through(user_id=emp.user_id, permission_id=pid) for pid in wanted_ids
            ], ignore_conflicts=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0069_portal_capabilities'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='staffaccess',
            name='denied_capabilities',
        ),
        migrations.RemoveField(
            model_name='staffaccess',
            name='extra_capabilities',
        ),
        migrations.DeleteModel(
            name='PortalCapability',
        ),
        migrations.CreateModel(
            name='PortalFeature',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'verbose_name': 'Portal huquqi',
                'verbose_name_plural': 'Portal huquqlari',
                'permissions': (
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
                ),
                'default_permissions': (),
            },
        ),
        migrations.RunPython(seed_portal_perms_from_roles, noop),
    ]
