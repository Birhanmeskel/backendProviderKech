import decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('drivers', '0006_add_payout_percentage'),
    ]

    operations = [
        migrations.AddField(
            model_name='driverprofile',
            name='balance_adjustment',
            field=models.DecimalField(
                decimal_places=2,
                default=decimal.Decimal('0.00'),
                max_digits=12,
            ),
        ),
        migrations.AddField(
            model_name='driverprofile',
            name='debt_adjustment',
            field=models.DecimalField(
                decimal_places=2,
                default=decimal.Decimal('0.00'),
                max_digits=12,
            ),
        ),
    ]
