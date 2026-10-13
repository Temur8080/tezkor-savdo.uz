from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0046_remove_installment_credit_officer'),
    ]

    operations = [
        migrations.AddField(
            model_name='appsettings',
            name='vat_enabled',
            field=models.BooleanField(
                default=True,
                help_text='Kassada QQS qo‘shilsinmi',
                verbose_name='QQS yoqilgan',
            ),
        ),
        migrations.AddField(
            model_name='appsettings',
            name='vat_percent',
            field=models.DecimalField(
                decimal_places=2,
                default=12,
                help_text='Masalan 12 = 12%',
                max_digits=5,
                verbose_name='QQS foizi',
            ),
        ),
    ]
