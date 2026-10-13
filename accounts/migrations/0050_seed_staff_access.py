from django.db import migrations


def seed_staff_access(apps, schema_editor):
    Employee = apps.get_model('accounts', 'Employee')
    StaffAccess = apps.get_model('accounts', 'StaffAccess')
    for emp in Employee.objects.select_related('user', 'branch').iterator():
        if not emp.branch_id or not getattr(emp.branch, 'organization_id', None):
            continue
        access, _ = StaffAccess.objects.get_or_create(user_id=emp.user_id)
        access.organizations.add(emp.branch.organization_id)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0049_staff_access_organizations'),
    ]

    operations = [
        migrations.RunPython(seed_staff_access, noop),
    ]
