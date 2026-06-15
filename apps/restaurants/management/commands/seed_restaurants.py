"""Idempotent dev seed for restaurant catalog (local/DEBUG only)."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.restaurants.models import MenuCategory, MenuItem, Restaurant

SEED_MARKER = "[seed_restaurants]"

RESTAURANTS = (
    {
        "name": "Café Arabe",
        "description": "Traditional Moroccan breakfast and mint tea.",
        "phone": "+212600111222",
        "address_text": "Rue Riad Zitoun, Marrakech",
        "latitude": Decimal("31.625700"),
        "longitude": Decimal("-7.989100"),
        "opening_hours": "08:00–22:00",
        "categories": (
            ("Breakfast", ("Msemen", "35.00"), ("Baghrir", "28.00")),
            ("Mains", ("Tagine Poulet", "85.00"), ("Couscous Royal", "95.00")),
        ),
    },
    {
        "name": "Le Jardin",
        "description": "Garden dining with fresh salads and grills.",
        "phone": "+212600333444",
        "address_text": "Gueliz, Marrakech",
        "latitude": Decimal("31.634200"),
        "longitude": Decimal("-8.008300"),
        "opening_hours": "11:00–23:00",
        "categories": (
            ("Starters", ("Harira", "35.00"), ("Zaalouk", "40.00")),
            ("Grill", ("Brochettes", "120.00"), ("Kefta", "90.00")),
        ),
    },
)


class Command(BaseCommand):
    help = "Seed sample restaurants, categories, and menu items (dev/local only, idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even when DEBUG is False (not recommended).",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "seed_restaurants is disabled when DEBUG=False. "
                "Use --force only in controlled environments."
            )

        created_restaurants = 0
        created_categories = 0
        created_items = 0

        for spec in RESTAURANTS:
            restaurant, was_created = Restaurant.objects.get_or_create(
                name=spec["name"],
                defaults={
                    "description": spec["description"],
                    "phone": spec["phone"],
                    "address_text": spec["address_text"],
                    "latitude": spec["latitude"],
                    "longitude": spec["longitude"],
                    "opening_hours": spec["opening_hours"],
                    "is_active": True,
                },
            )
            if was_created:
                created_restaurants += 1
            elif SEED_MARKER not in (restaurant.description or ""):
                restaurant.description = f"{restaurant.description}\n{SEED_MARKER}".strip()
                restaurant.save(update_fields=["description", "updated_at"])

            for sort_order, (category_name, *items) in enumerate(spec["categories"], start=1):
                category, cat_created = MenuCategory.objects.get_or_create(
                    restaurant=restaurant,
                    name=category_name,
                    defaults={"sort_order": sort_order, "is_active": True},
                )
                if cat_created:
                    created_categories += 1

                for item_order, (item_name, price) in enumerate(items, start=1):
                    _, item_created = MenuItem.objects.get_or_create(
                        restaurant=restaurant,
                        name=item_name,
                        defaults={
                            "category": category,
                            "description": f"{SEED_MARKER} sample item",
                            "price": Decimal(price),
                            "currency": "ETB",
                            "is_available": True,
                            "sort_order": item_order,
                        },
                    )
                    if item_created:
                        created_items += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complete: +{created_restaurants} restaurants, "
                f"+{created_categories} categories, +{created_items} items "
                f"(existing records left unchanged)."
            )
        )
