from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("restaurants", "0005_alter_restaurant_opening_hours"),
    ]

    operations = [
        migrations.AddField(
            model_name="menuitem",
            name="takeaway_box_price",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Per-unit takeaway box cost added to the item price.",
                max_digits=10,
            ),
        ),
    ]
