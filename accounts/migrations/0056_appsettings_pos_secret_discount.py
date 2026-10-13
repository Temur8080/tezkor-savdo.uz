from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0055_consultant_awaiting_approval'),
    ]

    operations = [
        migrations.AddField(
            model_name='appsettings',
            name='pos_secret_code',
            field=models.CharField(
                blank=True,
                default='9090',
                help_text='Kassada «Qabul qilingan naqd» maydoniga shu kod yozilsa chegirma qo‘llanadi',
                max_length=32,
                verbose_name='Kassa maxfiy kodi',
            ),
        ),
        migrations.AddField(
            model_name='appsettings',
            name='pos_secret_discount_percent',
            field=models.DecimalField(
                decimal_places=2,
                default=10,
                help_text='Maxfiy kod kiritilganda umumiy summadan chegirma foizi',
                max_digits=5,
                verbose_name='Maxfiy kod chegirmasi %',
            ),
        ),
    ]
