from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0058_theme_mode_system'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pricetier',
            name='kind',
            field=models.SlugField(
                db_index=True,
                default='regular',
                max_length=32,
                unique=True,
                verbose_name='Tur',
            ),
        ),
        migrations.AlterField(
            model_name='customer',
            name='customer_type',
            field=models.CharField(
                db_index=True,
                default='regular',
                max_length=32,
                verbose_name='Turi',
            ),
        ),
    ]
