from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("restaurants", "0004_restaurant_hours_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="restaurant",
            name="opening_hours",
            field=models.CharField(
                blank=True,
                help_text="Human-readable hours label (auto-generated from opens/closes when set).",
                max_length=255,
            ),
        ),
    ]
