from __future__ import annotations

from django.db.models import Count, Prefetch, Q
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.restaurants.models import MenuCategory, MenuItem, Restaurant
from apps.restaurants.permissions import IsRestaurantAdmin, IsRestaurantStaffRead
from apps.restaurants.services.menu import MenuServiceError, create_category, create_menu_item, delete_category, delete_menu_item, update_category, update_menu_item
from apps.restaurants.services.restaurant import RestaurantServiceError, create_restaurant, delete_restaurant, update_restaurant
from .serializers import (
    MenuCategorySerializer,
    MenuItemSerializer,
    MenuItemWriteSerializer,
    PublicCatalogItemSerializer,
    PublicMenuCategorySerializer,
    RestaurantListSerializer,
    RestaurantWriteSerializer,
)


def _staff_user(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user.role in ("admin", "sales"))


def _restaurant_queryset(request, *, for_list: bool = False):
    qs = Restaurant.objects.annotate(
        menu_item_count=Count("menu_items", distinct=True),
    )
    if _staff_user(request):
        return qs.order_by("-updated_at")
    return qs.filter(is_active=True).order_by("-updated_at")


class RestaurantListCreateView(APIView):
    """
    GET /api/v1/restaurants/ — public active list; staff sees all.
    POST — admin create.
    """

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsRestaurantAdmin()]
        return [AllowAny()]

    def get(self, request, *args, **kwargs):
        qs = _restaurant_queryset(request, for_list=True)
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(address_text__icontains=search)
                | Q(phone__icontains=search)
                | Q(menu_items__name__icontains=search)
            ).distinct()
        category = (request.query_params.get("category") or "").strip()
        if category:
            qs = qs.filter(
                menu_categories__name__iexact=category,
                menu_categories__is_active=True,
            ).distinct()
        serializer = RestaurantListSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        body = RestaurantWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            restaurant = create_restaurant(**body.validated_data)
        except RestaurantServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)
        return Response(
            RestaurantListSerializer(restaurant, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class PublicMenuCategoryNamesView(APIView):
    """
    GET /api/v1/restaurants/menu-categories/ — distinct active menu category
    names across active restaurants. Powers the customer home category filters.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        raw_names = (
            MenuCategory.objects.filter(is_active=True, restaurant__is_active=True)
            .values_list("name", flat=True)
        )
        # Case-insensitive de-duplication; keep the first-seen display casing.
        unique: dict[str, str] = {}
        for name in raw_names:
            cleaned = (name or "").strip()
            if not cleaned:
                continue
            unique.setdefault(cleaned.lower(), cleaned)
        ordered = sorted(unique.values(), key=lambda value: value.lower())
        return Response(ordered)


class PublicMenuItemsView(APIView):
    """
    GET /api/v1/restaurants/menu-items/?category=<name> — available menu items
    across active restaurants, optionally filtered to one category name. Powers
    the cross-restaurant category browse on the customer home.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        qs = (
            MenuItem.objects.filter(is_available=True, restaurant__is_active=True)
            .select_related("restaurant", "category")
            .order_by("name")
        )
        category = (request.query_params.get("category") or "").strip()
        if category:
            qs = qs.filter(category__name__iexact=category, category__is_active=True)
        serializer = PublicCatalogItemSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)


class RestaurantDetailView(APIView):
    """GET/PATCH/DELETE /api/v1/restaurants/{id}/"""

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsRestaurantAdmin()]

    def get_object(self, request, restaurant_id: int) -> Restaurant | None:
        try:
            restaurant = Restaurant.objects.annotate(
                menu_item_count=Count("menu_items", distinct=True),
            ).get(pk=restaurant_id)
        except Restaurant.DoesNotExist:
            return None
        if not _staff_user(request) and not restaurant.is_active:
            return None
        return restaurant

    def get(self, request, restaurant_id: int, *args, **kwargs):
        restaurant = self.get_object(request, restaurant_id)
        if restaurant is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(RestaurantListSerializer(restaurant, context={"request": request}).data)

    def patch(self, request, restaurant_id: int, *args, **kwargs):
        restaurant = self.get_object(request, restaurant_id)
        if restaurant is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        body = RestaurantWriteSerializer(restaurant, data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        try:
            restaurant = update_restaurant(restaurant, **body.validated_data)
        except RestaurantServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)
        return Response(RestaurantListSerializer(restaurant, context={"request": request}).data)

    def delete(self, request, restaurant_id: int, *args, **kwargs):
        restaurant = self.get_object(request, restaurant_id)
        if restaurant is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        delete_restaurant(restaurant)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RestaurantMenuView(APIView):
    """GET /api/v1/restaurants/{id}/menu/ — nested categories + available items."""

    permission_classes = [AllowAny]

    def get(self, request, restaurant_id: int, *args, **kwargs):
        try:
            restaurant = Restaurant.objects.get(pk=restaurant_id)
        except Restaurant.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _staff_user(request) and not restaurant.is_active:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        active_items = MenuItem.objects.filter(is_available=True).order_by("sort_order", "name")
        categories = (
            MenuCategory.objects.filter(restaurant=restaurant, is_active=True)
            .prefetch_related(Prefetch("items", queryset=active_items, to_attr="active_items"))
            .order_by("sort_order", "name")
        )

        return Response(
            {
                "restaurant_id": restaurant.id,
                "restaurant_name": restaurant.name,
                "categories": PublicMenuCategorySerializer(
                    categories, many=True, context={"request": request}
                ).data,
            }
        )


class MenuCategoryListCreateView(APIView):
    """GET/POST /api/v1/restaurants/{restaurant_id}/categories/"""

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsRestaurantAdmin()]
        return [IsRestaurantStaffRead()]

    def get(self, request, restaurant_id: int, *args, **kwargs):
        if not Restaurant.objects.filter(pk=restaurant_id).exists():
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        qs = MenuCategory.objects.filter(restaurant_id=restaurant_id).order_by("sort_order", "name")
        if not _staff_user(request):
            qs = qs.filter(is_active=True)
        return Response(MenuCategorySerializer(qs, many=True).data)

    def post(self, request, restaurant_id: int, *args, **kwargs):
        body = MenuCategorySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            category = create_category(restaurant_id=restaurant_id, **body.validated_data)
        except MenuServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)
        return Response(MenuCategorySerializer(category).data, status=status.HTTP_201_CREATED)


class MenuCategoryDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [IsRestaurantStaffRead()]
        return [IsRestaurantAdmin()]

    def patch(self, request, restaurant_id: int, category_id: int, *args, **kwargs):
        try:
            category = MenuCategory.objects.get(pk=category_id, restaurant_id=restaurant_id)
        except MenuCategory.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        body = MenuCategorySerializer(category, data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        try:
            category = update_category(category, **body.validated_data)
        except MenuServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)
        return Response(MenuCategorySerializer(category).data)

    def delete(self, request, restaurant_id: int, category_id: int, *args, **kwargs):
        try:
            category = MenuCategory.objects.get(pk=category_id, restaurant_id=restaurant_id)
        except MenuCategory.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        delete_category(category)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MenuItemListCreateView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsRestaurantAdmin()]
        return [IsRestaurantStaffRead()]

    def get(self, request, restaurant_id: int, *args, **kwargs):
        if not Restaurant.objects.filter(pk=restaurant_id).exists():
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        qs = MenuItem.objects.filter(restaurant_id=restaurant_id).select_related("category").order_by(
            "sort_order", "name"
        )
        category_id = request.query_params.get("category_id")
        if category_id:
            qs = qs.filter(category_id=category_id)
        if not _staff_user(request):
            qs = qs.filter(is_available=True, category__is_active=True)
        return Response(MenuItemSerializer(qs, many=True, context={"request": request}).data)

    def post(self, request, restaurant_id: int, *args, **kwargs):
        body = MenuItemWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            item = create_menu_item(
                restaurant_id=restaurant_id,
                category_id=data.pop("category_id"),
                **data,
            )
        except MenuServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)
        return Response(
            MenuItemSerializer(item, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class MenuItemDetailView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsRestaurantStaffRead()]
        return [IsRestaurantAdmin()]

    def patch(self, request, restaurant_id: int, item_id: int, *args, **kwargs):
        try:
            item = MenuItem.objects.select_related("category").get(pk=item_id, restaurant_id=restaurant_id)
        except MenuItem.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        body = MenuItemWriteSerializer(item, data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        try:
            item = update_menu_item(item, **body.validated_data)
        except MenuServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)
        return Response(MenuItemSerializer(item, context={"request": request}).data)

    def delete(self, request, restaurant_id: int, item_id: int, *args, **kwargs):
        try:
            item = MenuItem.objects.get(pk=item_id, restaurant_id=restaurant_id)
        except MenuItem.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        delete_menu_item(item)
        return Response(status=status.HTTP_204_NO_CONTENT)

