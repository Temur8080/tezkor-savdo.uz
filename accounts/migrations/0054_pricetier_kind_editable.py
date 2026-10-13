from django.db import migrations, models


def fill_kind(apps, schema_editor):
    PriceTier = apps.get_model('accounts', 'PriceTier')
    for tier in PriceTier.objects.all():
        if tier.code in ('regular', 'loyal', 'partner'):
            tier.kind = tier.code
        elif not getattr(tier, 'kind', None):
            tier.kind = 'regular'
        tier.save(update_fields=['kind'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0053_loyalty_partners'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricetier',
            name='kind',
            field=models.CharField(
                choices=[
                    ('regular', 'Oddiy mijoz'),
                    ('loyal', 'Sodiq mijoz'),
                    ('partner', 'Hamkor / Usta'),
                ],
                default='regular',
                help_text='Tizim ichki turi (o‘zgarmaydi). Kod va foizni qo‘lda o‘zgartirish mumkin.',
                max_length=20,
                verbose_name='Tizim turi',
            ),
        ),
        migrations.RunPython(fill_kind, noop),
        migrations.AlterField(
            model_name='pricetier',
            name='kind',
            field=models.CharField(
                choices=[
                    ('regular', 'Oddiy mijoz'),
                    ('loyal', 'Sodiq mijoz'),
                    ('partner', 'Hamkor / Usta'),
                ],
                help_text='Tizim ichki turi (o‘zgarmaydi). Kod va foizni qo‘lda o‘zgartirish mumkin.',
                max_length=20,
                unique=True,
                verbose_name='Tizim turi',
            ),
        ),
        migrations.AlterField(
            model_name='pricetier',
            name='code',
            field=models.SlugField(
                help_text='Qo‘lda o‘zgartirish mumkin (masalan loyal, vip, usta)',
                max_length=32,
                unique=True,
                verbose_name='Kod',
            ),
        ),
        migrations.AlterField(
            model_name='pricetier',
            name='discount_percent',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Qo‘lda kiriting — masalan 5 = 5%, 12.5 = 12,5%',
                max_digits=5,
                verbose_name='Chegirma %',
            ),
        ),
    ]
