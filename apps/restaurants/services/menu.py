"""Menu category and item write operations."""

from __future__ import annotations

from django.db import transaction

from apps.restaurants.models import MenuCategory, MenuItem, Restaurant


class MenuServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _get_restaurant(restaurant_id: int) -> Restaurant:
    try:
        return Restaurant.objects.get(pk=restaurant_id)
    except Restaurant.DoesNotExist as exc:
        raise MenuServiceError("Restaurant not found.", status_code=404) from exc


@transaction.atomic
def create_category(*, restaurant_id: int, **fields) -> MenuCategory:
    restaurant = _get_restaurant(restaurant_id)
    name = (fields.get("name") or "").strip()
    if not name:
        raise MenuServiceError("Category name is required.")
    if MenuCategory.objects.filter(restaurant=restaurant, name__iexact=name).exists():
        raise MenuServiceError("Category already exists for this restaurant.", status_code=409)
    return MenuCategory.objects.create(restaurant=restaurant, name=name, **{k: v for k, v in fields.items() if k != "name"})


@transaction.atomic
def update_category(category: MenuCategory, **fields) -> MenuCategory:
    if "name" in fields:
        name = (fields["name"] or "").strip()
        if not name:
            raise MenuServiceError("Category name is required.")
        if (
            MenuCategory.objects.filter(restaurant_id=category.restaurant_id, name__iexact=name)
            .exclude(pk=category.pk)
            .exists()
        ):
            raise MenuServiceError("Category already exists for this restaurant.", status_code=409)
        fields["name"] = name
    for key, value in fields.items():
        setattr(category, key, value)
    category.save()
    return category


def delete_category(category: MenuCategory) -> None:
    category.delete()


@transaction.atomic
def create_menu_item(*, restaurant_id: int, category_id: int, **fields) -> MenuItem:
    restaurant = _get_restaurant(restaurant_id)
    try:
        category = MenuCategory.objects.get(pk=category_id, restaurant=restaurant)
    except MenuCategory.DoesNotExist as exc:
        raise MenuServiceError("Category not found for this restaurant.", status_code=404) from exc

    name = (fields.get("name") or "").strip()
    if not name:
        raise MenuServiceError("Item name is required.")
    if MenuItem.objects.filter(restaurant=restaurant, name__iexact=name).exists():
        raise MenuServiceError("Menu item already exists for this restaurant.", status_code=409)

    return MenuItem.objects.create(restaurant=restaurant, category=category, name=name, **{k: v for k, v in fields.items() if k != "name"})


@transaction.atomic
def update_menu_item(item: MenuItem, **fields) -> MenuItem:
    if "category_id" in fields:
        try:
            category = MenuCategory.objects.get(pk=fields["category_id"], restaurant_id=item.restaurant_id)
        except MenuCategory.DoesNotExist as exc:
            raise MenuServiceError("Category not found for this restaurant.", status_code=404) from exc
        item.category = category
        del fields["category_id"]

    if "name" in fields:
        name = (fields["name"] or "").strip()
        if not name:
            raise MenuServiceError("Item name is required.")
        if MenuItem.objects.filter(restaurant_id=item.restaurant_id, name__iexact=name).exclude(pk=item.pk).exists():
            raise MenuServiceError("Menu item already exists for this restaurant.", status_code=409)
        fields["name"] = name

    for key, value in fields.items():
        setattr(item, key, value)
    item.save()
    return item


def delete_menu_item(item: MenuItem) -> None:
    item.delete()
