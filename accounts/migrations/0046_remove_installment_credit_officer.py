from django.db import migrations, models


def remap_installment_data(apps, schema_editor):
    Employee = apps.get_model('accounts', 'Employee')
    Order = apps.get_model('accounts', 'Order')
    Payment = apps.get_model('accounts', 'Payment')
    SalesAgent = apps.get_model('accounts', 'SalesAgent')

    Employee.objects.filter(role='Credit Officer').update(role='Sales Agent')
    Order.objects.filter(payment_method='INSTALLMENT').update(payment_method='CASH')
    Payment.objects.filter(payment_type='INSTALLMENT').update(payment_type='CASH')

    # Credit Officer xodimlar uchun SalesAgent yozuvi bo‘lmasa — yaratamiz
    for emp in Employee.objects.filter(role='Sales Agent'):
        SalesAgent.objects.get_or_create(
            employee_id=emp.id,
            defaults={
                'commission_rate': 0,
                'total_commission_earned': 0,
                'total_sales': 0,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0045_warranty_periods'),
    ]

    operations = [
        migrations.RunPython(remap_installment_data, migrations.RunPython.noop),
        migrations.DeleteModel(name='InstallmentPlan'),
        migrations.DeleteModel(name='CreditOfficer'),
        migrations.AlterField(
            model_name='employee',
            name='role',
            field=models.CharField(
                choices=[('Sales Agent', 'Sotuvchi'), ('Manager', 'Menejer')],
                default='Sales Agent',
                max_length=100,
                verbose_name='Lavozim',
            ),
        ),
        migrations.AlterField(
            model_name='order',
            name='payment_method',
            field=models.CharField(
                choices=[('CASH', 'Naqd')],
                max_length=100,
                verbose_name='To‘lov usuli',
            ),
        ),
        migrations.AlterField(
            model_name='payment',
            name='payment_type',
            field=models.CharField(
                choices=[('CASH', 'Naqd')],
                max_length=100,
                verbose_name='To‘lov turi',
            ),
        ),
    ]
