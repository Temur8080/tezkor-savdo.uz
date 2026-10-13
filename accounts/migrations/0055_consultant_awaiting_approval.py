from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0054_pricetier_kind_editable'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employee',
            name='role',
            field=models.CharField(
                choices=[
                    ('Sales Agent', 'Sotuvchi'),
                    ('Consultant', 'Maslahatchi'),
                    ('Manager', 'Menejer'),
                ],
                default='Sales Agent',
                max_length=100,
                verbose_name='Lavozim',
            ),
        ),
        migrations.AlterField(
            model_name='order',
            name='order_status',
            field=models.CharField(
                choices=[
                    ('AwaitingApproval', 'Tasdiqlash kutilmoqda'),
                    ('Pending', 'Kutilmoqda'),
                    ('Completed', 'Yakunlangan'),
                    ('Cancelled', 'Bekor qilingan'),
                ],
                default='Pending',
                max_length=100,
                verbose_name='Holat',
            ),
        ),
    ]
