"""Restaurant write operations (business rules outside views)."""

from __future__ import annotations

import os

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.restaurants.models import Restaurant
from apps.restaurants.services.hours import format_hours_display


class RestaurantServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _ensure_media_root() -> None:
    media_root = getattr(settings, "MEDIA_ROOT", None)
    if not media_root:
        return
    os.makedirs(media_root, exist_ok=True)
    # Pre-create common upload trees (helps when parent dir is writable but umask blocks subdirs).
    for sub in ("restaurants", "menu_items"):
        os.makedirs(os.path.join(media_root, sub), exist_ok=True)


def _sync_opening_hours_label(fields: dict) -> None:
    if "opens_at" not in fields and "closes_at" not in fields:
        return
    fields["opening_hours"] = format_hours_display(
        fields.get("opens_at"),
        fields.get("closes_at"),
    )


def _pop_image_fields(fields: dict) -> tuple[object | None, object | None]:
    logo = fields.pop("logo", None)
    cover_image = fields.pop("cover_image", None)
    return logo, cover_image


def _save_restaurant_images(restaurant: Restaurant, *, logo, cover_image) -> None:
    update_fields: list[str] = []
    if logo is not None:
        restaurant.logo = logo
        update_fields.append("logo")
    if cover_image is not None:
        restaurant.cover_image = cover_image
        update_fields.append("cover_image")
    if not update_fields:
        return
    try:
        restaurant.save(update_fields=[*update_fields, "updated_at"])
    except (OSError, ValueError) as exc:
        if isinstance(exc, PermissionError) or (isinstance(exc, OSError) and exc.errno == 13):
            raise RestaurantServiceError(
                "Could not save images: the server media directory is not writable. "
                "If using Docker, rebuild and restart containers (entrypoint fixes volume permissions).",
                status_code=503,
            ) from exc
        raise RestaurantServiceError(
            f"Could not save restaurant images: {exc}",
            status_code=400,
        ) from exc


@transaction.atomic
def create_restaurant(**fields) -> Restaurant:
    name = (fields.get("name") or "").strip()
    if not name:
        raise RestaurantServiceError("Restaurant name is required.")
    if Restaurant.objects.filter(name__iexact=name).exists():
        raise RestaurantServiceError("A restaurant with this name already exists.", status_code=409)

    _ensure_media_root()
    logo, cover_image = _pop_image_fields(fields)
    _sync_opening_hours_label(fields)

    try:
        restaurant = Restaurant.objects.create(**fields)
    except IntegrityError as exc:
        raise RestaurantServiceError(
            "A restaurant with this name already exists.",
            status_code=409,
        ) from exc

    _save_restaurant_images(restaurant, logo=logo, cover_image=cover_image)
    return restaurant


@transaction.atomic
def update_restaurant(restaurant: Restaurant, **fields) -> Restaurant:
    if "name" in fields:
        name = (fields["name"] or "").strip()
        if not name:
            raise RestaurantServiceError("Restaurant name is required.")
        if Restaurant.objects.filter(name__iexact=name).exclude(pk=restaurant.pk).exists():
            raise RestaurantServiceError("A restaurant with this name already exists.", status_code=409)
        fields["name"] = name

    _ensure_media_root()
    logo, cover_image = _pop_image_fields(fields)
    _sync_opening_hours_label(fields)

    for key, value in fields.items():
        setattr(restaurant, key, value)

    try:
        if fields:
            restaurant.save()
    except IntegrityError as exc:
        raise RestaurantServiceError(
            "A restaurant with this name already exists.",
            status_code=409,
        ) from exc

    _save_restaurant_images(restaurant, logo=logo, cover_image=cover_image)
    return restaurant


def delete_restaurant(restaurant: Restaurant) -> None:
    restaurant.delete()
