from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0047_appsettings_vat'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomerDebt',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('currency', models.CharField(choices=[('UZS', 'So‘m'), ('USD', 'Dollar')], default='UZS', max_length=3, verbose_name='Valyuta')),
                ('original_amount', models.DecimalField(decimal_places=2, max_digits=14, verbose_name='Dastlabki qarz')),
                ('paid_amount', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='To‘langan')),
                ('remaining_balance', models.DecimalField(decimal_places=2, max_digits=14, verbose_name='Qolgan qarz')),
                ('status', models.CharField(choices=[('Open', 'Ochiq'), ('Partial', 'Qisman'), ('Paid', 'To‘langan')], default='Open', max_length=20, verbose_name='Holat')),
                ('note', models.CharField(blank=True, max_length=255, verbose_name='Izoh')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Yangilangan')),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.branch', verbose_name='Filial')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_debts', to='accounts.employee', verbose_name='Yaratgan')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='debts', to='accounts.customer', verbose_name='Mijoz')),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='debts', to='accounts.order', verbose_name='Buyurtma')),
            ],
            options={
                'verbose_name': 'Qarzdor',
                'verbose_name_plural': 'Qarzdorlar',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DebtPayment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14, verbose_name='Summa')),
                ('paid_at', models.DateTimeField(auto_now_add=True, verbose_name='To‘lov vaqti')),
                ('note', models.CharField(blank=True, max_length=255, verbose_name='Izoh')),
                ('debt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='accounts.customerdebt', verbose_name='Qarz')),
                ('received_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='accounts.employee', verbose_name='Qabul qilgan')),
            ],
            options={
                'verbose_name': 'Qarz to‘lovi',
                'verbose_name_plural': 'Qarz to‘lovlari',
                'ordering': ['-paid_at'],
            },
        ),
    ]
