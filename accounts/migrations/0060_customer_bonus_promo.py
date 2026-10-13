from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0059_pricetier_custom_kinds'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='bonus_discount_percent',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                help_text='Tur chegirmasidan yuqori bo‘lsa, kassada shu foiz qo‘llanadi',
                max_digits=5,
                verbose_name='Shaxsiy aksiya %',
            ),
        ),
        migrations.AddField(
            model_name='customer',
            name='notes',
            field=models.CharField(blank=True, max_length=255, verbose_name='Izoh'),
        ),
    ]
