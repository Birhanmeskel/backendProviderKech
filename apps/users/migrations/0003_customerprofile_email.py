from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_salesprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="customerprofile",
            name="email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
    ]
