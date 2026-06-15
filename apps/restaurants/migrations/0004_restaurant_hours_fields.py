from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("restaurants", "0003_menuitem_currency_etb"),
    ]

    operations = [
        migrations.AddField(
            model_name="restaurant",
            name="opens_at",
            field=models.TimeField(
                blank=True,
                help_text="Local opening time (Africa/Addis_Ababa).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="restaurant",
            name="closes_at",
            field=models.TimeField(
                blank=True,
                help_text="Local closing time (Africa/Addis_Ababa).",
                null=True,
            ),
        ),
    ]
