import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("orders", "0002_milestone5_driver_delivery"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="ETB", max_length=8)),
                ("chapa_tx_ref", models.CharField(db_index=True, max_length=128, unique=True)),
                ("chapa_reference", models.CharField(blank=True, db_index=True, max_length=128)),
                ("payment_method", models.CharField(blank=True, max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("success", "Success"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                            ("refunded", "Refunded"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("checkout_url", models.URLField(blank=True, max_length=512)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("raw_initialize_response", models.JSONField(blank=True, default=dict)),
                ("raw_verify_response", models.JSONField(blank=True, default=dict)),
                ("raw_webhook_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payments",
                        to="orders.order",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(fields=["customer", "-created_at"], name="payments_pa_custome_idx"),
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(fields=["order", "status"], name="payments_pa_order_i_idx"),
        ),
    ]
