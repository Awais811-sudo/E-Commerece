from .views import *
def cart_count(request):
    """Returns the number of items in the user's cart (authenticated) or session-based cart (guest)."""
    if request.user.is_authenticated:
        cart_obj = request.user.cart.first()  # Get the first active cart instance
        count = cart_obj.items.count() if cart_obj else 0
    else:
        cart = request.session.get('cart', {})  # Guest cart stored in session
        count = sum(cart.values())  # If cart stores {product_id: quantity}, count total items
    return {'cart_count': count}


def wishlist_count_processor(request):
    if request.user.is_authenticated:
        wishlist_obj = get_user_wishlist(request.user)
        wishlist_count = WishlistItem.objects.filter(wishlist=wishlist_obj).count()
    else:
        wishlist_count = len(request.session.get('wishlist', []))

    return {'wishlist_count': wishlist_count}



