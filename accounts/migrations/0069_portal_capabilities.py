from django.db import migrations, models


def seed_capabilities(apps, schema_editor):
    PortalCapability = apps.get_model('accounts', 'PortalCapability')
    caps = (
        ('multi_branch', 'Ko‘p filial / menejer ko‘rinishi', 10),
        ('dashboard', 'Boshqaruv', 20),
        ('pos', 'Kassa', 30),
        ('sales', 'Sotuvlar', 40),
        ('inventory', 'Ombor', 50),
        ('reports', 'Hisobotlar', 60),
        ('customers', 'Mijozlar', 70),
        ('inventory_intake', 'Ombor kirimi', 80),
        ('employees', 'Xodimlar', 90),
        ('warranty', 'Kafolat', 100),
        ('returns', 'Qaytarishlar', 110),
        ('debtors', 'Qarzdorlar', 120),
        ('reservations', 'Bronlar', 130),
        ('expenses', 'Xarajatlar', 140),
        ('audit', 'Audit', 150),
        ('settings', 'Sozlamalar', 160),
        ('sale_complete', 'Sotuvni yakunlash', 170),
        ('return_process', 'Qaytarishni amalga oshirish', 180),
    )
    for code, name, order in caps:
        PortalCapability.objects.update_or_create(
            code=code,
            defaults={'name': name, 'sort_order': order},
        )


def unseed_capabilities(apps, schema_editor):
    PortalCapability = apps.get_model('accounts', 'PortalCapability')
    PortalCapability.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0068_product_sale_discount'),
    ]

    operations = [
        migrations.CreateModel(
            name='PortalCapability',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.SlugField(max_length=64, unique=True, verbose_name='Kod')),
                ('name', models.CharField(max_length=120, verbose_name='Nomi')),
                ('sort_order', models.PositiveSmallIntegerField(default=0, verbose_name='Tartib')),
            ],
            options={
                'verbose_name': 'Portal huquqi',
                'verbose_name_plural': 'Portal huquqlari',
                'ordering': ('sort_order', 'code'),
            },
        ),
        migrations.AddField(
            model_name='staffaccess',
            name='denied_capabilities',
            field=models.ManyToManyField(
                blank=True,
                help_text='Lavozim bersa ham yopiladigan bo‘limlar.',
                related_name='denied_to_users',
                to='accounts.portalcapability',
                verbose_name='Roldan olib tashlangan huquqlar',
            ),
        ),
        migrations.AddField(
            model_name='staffaccess',
            name='extra_capabilities',
            field=models.ManyToManyField(
                blank=True,
                help_text='Lavozim berganidan tashqari ochiladigan bo‘limlar.',
                related_name='granted_to_users',
                to='accounts.portalcapability',
                verbose_name='Rolga qo‘shimcha huquqlar',
            ),
        ),
        migrations.RunPython(seed_capabilities, unseed_capabilities),
    ]
