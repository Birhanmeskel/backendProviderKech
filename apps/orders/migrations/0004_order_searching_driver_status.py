from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0003_order_pricing_breakdown"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("confirmed", "Confirmed"),
                    ("searching_driver", "Searching driver"),
                    ("preparing", "Preparing"),
                    ("ready_for_pickup", "Ready for pickup"),
                    ("assigned", "Assigned"),
                    ("picked_up", "Picked up"),
                    ("delivering", "Delivering"),
                    ("delivered", "Delivered"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="pending",
                max_length=32,
            ),
        ),
    ]
