import decimal

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('drivers', '0005_milestone5_driver_delivery'),
    ]

    operations = [
        migrations.AddField(
            model_name='driverprofile',
            name='payout_percentage',
            field=models.DecimalField(
                decimal_places=2,
                default=decimal.Decimal('60.00'),
                help_text='Percentage of delivery fee the driver receives (0–100).',
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(decimal.Decimal('0')),
                    django.core.validators.MaxValueValidator(decimal.Decimal('100')),
                ],
            ),
        ),
    ]
