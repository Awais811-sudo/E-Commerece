from django.urls import path
from . import views
from .views import * 

urlpatterns = [
        # Profile & Address Management
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/address/manage/', views.manage_address, name='manage_address'),
    path('profile/address/manage/<int:address_id>/', views.manage_address, name='edit_address'),
    path('orders/history/', OrderHistoryView.as_view(), name='order_history'),  # ✅ Add this

    # Checkout & Order Handling
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('order/confirmation/<int:order_id>/', views.OrderConfirmationView.as_view(), name='order_confirmation'),
    path('order/<int:order_id>/', views.OrderDetailView.as_view(), name='order_detail'),
    path("logout/", views.logout_view, name="logout_view"),
    path('search/', views.search_view, name='search'),
    path('autocomplete/', views.autocomplete, name='autocomplete'),
    path('', views.home, name='home'),
    path('product/<slug:slug>/', views.product_detail, name='product_detail'),
    path('product/<slug:slug>/review/', views.add_review, name='add_review'),
    path('shop/', views.shop, name='shop'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.user_login, name='login'),
    path('cart/update/<int:product_id>/<str:action>/', views.update_cart, name='update_cart'),
    path('add_to_cart/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/remove/<int:product_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/', views.cart, name='cart'),
    path('wishlist/', views.wishlist, name='wishlist'),
    path('wishlist/add/<int:product_id>/', views.add_to_wishlist, name='add_to_wishlist'),
    path('address/', views.manage_address, name='manage_address'),
    path('address/<int:address_id>/', views.manage_address, name='manage_address'),
    path('wishlist/add/<int:product_id>/', views.add_to_wishlist, name='add_to_wishlist'),
    path('wishlist/delete/<int:item_id>/', views.delete_wishlist_item, name='delete_wishlist_item'),




    # DASBOARD
    path('dashboard/', admin_dashboard, name='dashboard'),

    path('orders/', views.order_list, name='order_list'),
    path('orders/<int:order_id>/update-status/', views.update_order_status, name='update_order_status'),
    path('orders/<int:order_id>/cancel/', views.cancel_order, name='cancel_order'),
    # path('orders/<int:pk>/', views.order_detail, name='order_detail'),
    
]