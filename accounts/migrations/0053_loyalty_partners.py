from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


def seed_price_tiers(apps, schema_editor):
    PriceTier = apps.get_model('accounts', 'PriceTier')
    defaults = (
        ('regular', 'Oddiy', Decimal('0.00')),
        ('loyal', 'Sodiq mijoz', Decimal('5.00')),
        ('partner', 'Hamkor / Usta', Decimal('10.00')),
    )
    for code, name, pct in defaults:
        PriceTier.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'discount_percent': pct,
                'is_active': True,
            },
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0052_expense_model'),
    ]

    operations = [
        migrations.CreateModel(
            name='PriceTier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.SlugField(max_length=32, unique=True, verbose_name='Kod')),
                ('name', models.CharField(max_length=80, verbose_name='Nomi')),
                ('discount_percent', models.DecimalField(
                    decimal_places=2, default=Decimal('0.00'),
                    help_text='Masalan 5 = 5% arzon', max_digits=5, verbose_name='Chegirma %',
                )),
                ('is_active', models.BooleanField(default=True, verbose_name='Faol')),
            ],
            options={
                'verbose_name': 'Narx darajasi',
                'verbose_name_plural': 'Narx darajalari',
                'ordering': ['discount_percent', 'name'],
            },
        ),
        migrations.AddField(
            model_name='customer',
            name='customer_type',
            field=models.CharField(
                choices=[
                    ('regular', 'Oddiy mijoz'),
                    ('loyal', 'Sodiq mijoz'),
                    ('partner', 'Hamkor / Usta'),
                ],
                db_index=True,
                default='regular',
                max_length=20,
                verbose_name='Turi',
            ),
        ),
        migrations.AddField(
            model_name='customer',
            name='price_tier',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='customers', to='accounts.pricetier', verbose_name='Narx darajasi',
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='partner',
            field=models.ForeignKey(
                blank=True, help_text='Mijozni olib kelgan usta yoki hamkor',
                limit_choices_to={'customer_type': 'partner', 'is_active': True},
                null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='referred_orders', to='accounts.customer', verbose_name='Hamkor / usta',
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='list_total',
            field=models.DecimalField(decimal_places=2, default=0.00, max_digits=14, verbose_name='Chegirmasiz jami'),
        ),
        migrations.AddField(
            model_name='order',
            name='discount_percent',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=5, verbose_name='Chegirma %'),
        ),
        migrations.AddField(
            model_name='order',
            name='discount_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14, verbose_name='Chegirma summa'),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='list_unit_price',
            field=models.DecimalField(decimal_places=2, default=0.00, max_digits=14, verbose_name='Asl birlik narxi'),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='discount_percent',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=5, verbose_name='Chegirma %'),
        ),
        migrations.RunPython(seed_price_tiers, noop_reverse),
    ]
