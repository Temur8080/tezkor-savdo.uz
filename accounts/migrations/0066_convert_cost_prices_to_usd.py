from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models


def convert_costs_to_usd(apps, schema_editor):
    Product = apps.get_model('accounts', 'Product')
    AppSettings = apps.get_model('accounts', 'AppSettings')

    settings_obj = AppSettings.objects.order_by('pk').first()
    rate = Decimal(str(getattr(settings_obj, 'usd_to_uzs', None) or '12000'))
    if rate <= 0:
        rate = Decimal('12000')

    for product in Product.objects.all().iterator():
        amount = Decimal(str(product.cost_price or 0))
        cur = (product.cost_currency or 'UZS').upper()

        # So‘mda saqlangan tannarx → dollar (noto‘g‘ri USD belgilangan katta summalar ham)
        if cur == 'UZS' or (cur == 'USD' and amount >= Decimal('500')):
            usd_amount = (amount / rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            product.cost_price = usd_amount
            product.cost_currency = 'USD'
            product.save(update_fields=['cost_price', 'cost_currency'])
        elif cur != 'USD':
            product.cost_currency = 'USD'
            product.save(update_fields=['cost_currency'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0065_product_unit_decimal_qty'),
    ]

    operations = [
        migrations.RunPython(convert_costs_to_usd, noop_reverse),
        migrations.AlterField(
            model_name='product',
            name='cost_currency',
            field=models.CharField(
                choices=[('UZS', 'So‘m'), ('USD', 'Dollar')],
                default='USD',
                help_text='Tannarx shu valyutada saqlanadi (kirim valyutasi)',
                max_length=3,
                verbose_name='Tannarx valyutasi',
            ),
        ),
    ]
