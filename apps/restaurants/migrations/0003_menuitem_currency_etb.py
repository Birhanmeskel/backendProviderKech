from django.db import migrations, models


def mad_to_etb(apps, schema_editor):
    MenuItem = apps.get_model("restaurants", "MenuItem")
    MenuItem.objects.filter(currency="MAD").update(currency="ETB")


class Migration(migrations.Migration):

    dependencies = [
        ("restaurants", "0002_rename_restaurants__restaur_2e2f8a_idx_restaurants_restaur_d4034f_idx_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="menuitem",
            name="currency",
            field=models.CharField(default="ETB", max_length=8),
        ),
        migrations.RunPython(mad_to_etb, migrations.RunPython.noop),
    ]
