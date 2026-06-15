from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0005_merge_20260522_1225'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='payment_method',
            field=models.CharField(
                choices=[('chapa', 'Chapa'), ('pod', 'Pay on delivery')],
                default='chapa',
                db_index=True,
                max_length=16,
            ),
        ),
    ]
