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
                    ("preparing", "Preparing"),
                    ("ready_for_pickup", "Ready for pickup"),
                    ("assigned", "Assigned"),
                    ("declined", "Declined"),
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
        migrations.AlterField(
            model_name="driverdeliveryevent",
            name="action",
            field=models.CharField(
                choices=[
                    ("acknowledged", "Acknowledged"),
                    ("declined", "Declined"),
                    ("picked_up", "Picked up"),
                    ("started_delivery", "Started delivery"),
                    ("completed", "Completed"),
                ],
                max_length=32,
            ),
        ),
    ]
