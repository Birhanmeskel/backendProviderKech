# Driver onboarding: profile fields + documents

import apps.drivers.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("drivers", "0003_driverprofile_approval_audit_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="driverprofile",
            name="email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="driverprofile",
            name="vehicle_type",
            field=models.CharField(
                blank=True,
                choices=[("sedan", "Sedan"), ("motorbike", "Motorbike")],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="driverprofile",
            name="phone_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="driverprofile",
            name="documents_submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="DriverDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "document_type",
                    models.CharField(
                        choices=[
                            ("license", "Driver license"),
                            ("national_id", "National ID"),
                            ("vehicle_registration", "Vehicle registration"),
                            ("profile_photo", "Profile photo"),
                        ],
                        max_length=32,
                    ),
                ),
                ("file", models.FileField(upload_to=apps.drivers.models.driver_document_upload_to)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="driver_documents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "document_type"),
                        name="uniq_driver_document_per_type",
                    )
                ],
            },
        ),
    ]
