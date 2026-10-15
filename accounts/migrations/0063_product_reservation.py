from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0062_orderitem_price_adjusted'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductReservation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_name', models.CharField(max_length=150, verbose_name='Mijoz nomi')),
                ('phone', models.CharField(blank=True, max_length=30, verbose_name='Telefon')),
                ('currency', models.CharField(choices=[('UZS', 'So‘m'), ('USD', 'Dollar')], default='UZS', max_length=3, verbose_name='Valyuta')),
                ('total_amount', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='Jami summa')),
                ('item_count', models.PositiveIntegerField(default=0, verbose_name='Mahsulot soni')),
                ('unit_count', models.PositiveIntegerField(default=0, verbose_name='Jami dona')),
                ('status', models.CharField(choices=[('Active', 'Faol'), ('Cancelled', 'Bekor qilingan'), ('Completed', 'Yakunlangan')], default='Active', max_length=20, verbose_name='Holat')),
                ('note', models.CharField(blank=True, max_length=255, verbose_name='Izoh')),
                ('stock_held', models.BooleanField(default=True, verbose_name='Ombordan ushlab turilgan')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Yangilangan')),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.branch', verbose_name='Filial')),
                ('customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reservations', to='accounts.customer', verbose_name='Mijoz')),
                ('employee', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reservations', to='accounts.employee', verbose_name='Xodim')),
            ],
            options={
                'verbose_name': 'Bron',
                'verbose_name_plural': 'Bronlar',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ProductReservationItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(default=1, verbose_name='Miqdor')),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=14, verbose_name='Narx')),
                ('line_total', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='Qator jami')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='accounts.product', verbose_name='Mahsulot')),
                ('reservation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='accounts.productreservation', verbose_name='Bron')),
            ],
            options={
                'verbose_name': 'Bron qatori',
                'verbose_name_plural': 'Bron qatorlari',
            },
        ),
    ]
