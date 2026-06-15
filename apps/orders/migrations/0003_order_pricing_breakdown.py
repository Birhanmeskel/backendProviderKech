from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0002_milestone5_driver_delivery"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="driver_payout",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0.00"), max_digits=10
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="platform_fee",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0.00"), max_digits=10
            ),
        ),
    ]
