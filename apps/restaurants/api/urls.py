from django.urls import path

from .views import (
    MenuCategoryDetailView,
    MenuCategoryListCreateView,
    MenuItemDetailView,
    MenuItemListCreateView,
    PublicMenuCategoryNamesView,
    PublicMenuItemsView,
    RestaurantDetailView,
    RestaurantListCreateView,
    RestaurantMenuView,
)

urlpatterns = [
    path("", RestaurantListCreateView.as_view(), name="restaurant_list"),
    path(
        "menu-categories/",
        PublicMenuCategoryNamesView.as_view(),
        name="public_menu_categories",
    ),
    path(
        "menu-items/",
        PublicMenuItemsView.as_view(),
        name="public_menu_items",
    ),
    path("<int:restaurant_id>/", RestaurantDetailView.as_view(), name="restaurant_detail"),
    path("<int:restaurant_id>/menu/", RestaurantMenuView.as_view(), name="restaurant_menu"),
    path(
        "<int:restaurant_id>/categories/",
        MenuCategoryListCreateView.as_view(),
        name="restaurant_categories",
    ),
    path(
        "<int:restaurant_id>/categories/<int:category_id>/",
        MenuCategoryDetailView.as_view(),
        name="restaurant_category_detail",
    ),
    path(
        "<int:restaurant_id>/menu-items/",
        MenuItemListCreateView.as_view(),
        name="restaurant_menu_items",
    ),
    path(
        "<int:restaurant_id>/menu-items/<int:item_id>/",
        MenuItemDetailView.as_view(),
        name="restaurant_menu_item_detail",
    ),
]
