# Generated for Milestone 3 restaurant & menu catalog

import apps.restaurants.models
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Restaurant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, unique=True)),
                ("description", models.TextField(blank=True)),
                ("phone", models.CharField(blank=True, max_length=32)),
                ("address_text", models.CharField(blank=True, max_length=500)),
                (
                    "latitude",
                    models.DecimalField(
                        decimal_places=6,
                        max_digits=9,
                        validators=[
                            django.core.validators.MinValueValidator(-90),
                            django.core.validators.MaxValueValidator(90),
                        ],
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        decimal_places=6,
                        max_digits=9,
                        validators=[
                            django.core.validators.MinValueValidator(-180),
                            django.core.validators.MaxValueValidator(180),
                        ],
                    ),
                ),
                ("opening_hours", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("logo", models.ImageField(blank=True, null=True, upload_to=apps.restaurants.models.restaurant_logo_upload_to)),
                ("cover_image", models.ImageField(blank=True, null=True, upload_to=apps.restaurants.models.restaurant_cover_upload_to)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("-updated_at", "name")},
        ),
        migrations.CreateModel(
            name="MenuCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "restaurant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="menu_categories",
                        to="restaurants.restaurant",
                    ),
                ),
            ],
            options={"ordering": ("sort_order", "name")},
        ),
        migrations.CreateModel(
            name="MenuItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("currency", models.CharField(default="MAD", max_length=8)),
                ("is_available", models.BooleanField(db_index=True, default=True)),
                ("image", models.ImageField(blank=True, null=True, upload_to=apps.restaurants.models.menu_item_image_upload_to)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="restaurants.menucategory",
                    ),
                ),
                (
                    "restaurant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="menu_items",
                        to="restaurants.restaurant",
                    ),
                ),
            ],
            options={"ordering": ("sort_order", "name")},
        ),
        migrations.AddIndex(
            model_name="restaurant",
            index=models.Index(fields=["is_active", "-updated_at"], name="restaurants__is_acti_8f0b0d_idx"),
        ),
        migrations.AddConstraint(
            model_name="menucategory",
            constraint=models.UniqueConstraint(fields=("restaurant", "name"), name="uniq_menu_category_name_per_restaurant"),
        ),
        migrations.AddIndex(
            model_name="menucategory",
            index=models.Index(fields=["restaurant", "sort_order"], name="restaurants__restaur_2e2f8a_idx"),
        ),
        migrations.AddIndex(
            model_name="menucategory",
            index=models.Index(fields=["restaurant", "is_active"], name="restaurants__restaur_9a1c2b_idx"),
        ),
        migrations.AddConstraint(
            model_name="menuitem",
            constraint=models.UniqueConstraint(fields=("restaurant", "name"), name="uniq_menu_item_name_per_restaurant"),
        ),
        migrations.AddIndex(
            model_name="menuitem",
            index=models.Index(fields=["restaurant", "is_available"], name="restaurants__restaur_4d5e6f_idx"),
        ),
        migrations.AddIndex(
            model_name="menuitem",
            index=models.Index(fields=["category", "is_available"], name="restaurants__categor_7g8h9i_idx"),
        ),
    ]
