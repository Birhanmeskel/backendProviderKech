from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_normalize_user_phone"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="recovery_email",
            field=models.EmailField(
                blank=True,
                default="",
                help_text="Staff recovery email for password reset (admin/sales).",
                max_length=254,
            ),
        ),
    ]
