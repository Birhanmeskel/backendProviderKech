from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0006_order_payment_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="takeaway_box_price",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0.00"), max_digits=10
            ),
        ),
    ]
