from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0056_appsettings_pos_secret_discount'),
    ]

    operations = [
        migrations.AddField(
            model_name='appsettings',
            name='theme_mode',
            field=models.CharField(
                choices=[
                    ('auto', 'Avtomatik (soat bo‘yicha)'),
                    ('day', 'Kunduzgi (yorug‘)'),
                    ('night', 'Tungi (qorong‘u)'),
                ],
                default='auto',
                max_length=10,
                verbose_name='Interfeys rejimi',
            ),
        ),
        migrations.AddField(
            model_name='appsettings',
            name='theme_day_start',
            field=models.PositiveSmallIntegerField(
                default=6,
                help_text='0–23, avtomatik rejimda',
                verbose_name='Kunduz boshlanishi (soat)',
            ),
        ),
        migrations.AddField(
            model_name='appsettings',
            name='theme_night_start',
            field=models.PositiveSmallIntegerField(
                default=19,
                help_text='0–23, avtomatik rejimda',
                verbose_name='Kecha boshlanishi (soat)',
            ),
        ),
    ]
