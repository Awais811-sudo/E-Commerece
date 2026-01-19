# shop/context_processors.py
from .models import Cart, CartItem, Wishlist, WishlistItem

def cart_count(request):
    """Returns the number of items in the user's cart."""
    cart_count = 0
    
    if request.user.is_authenticated:
        # For logged-in users
        try:
            cart = Cart.objects.get(user=request.user)
            cart_items = CartItem.objects.filter(cart=cart)
            cart_count = sum(item.quantity for item in cart_items)
        except Cart.DoesNotExist:
            cart_count = 0
    else:
        # For guest users
        session_key = request.session.session_key
        if not session_key:
            request.session.create()
            session_key = request.session.session_key
        
        try:
            cart = Cart.objects.get(session_key=session_key)
            cart_items = CartItem.objects.filter(cart=cart)
            cart_count = sum(item.quantity for item in cart_items)
        except Cart.DoesNotExist:
            cart_count = 0
    
    return {'cart_count': cart_count}

def wishlist_count_processor(request):
    """Returns the number of items in the user's wishlist."""
    wishlist_count = 0
    
    if request.user.is_authenticated:
        # For logged-in users
        try:
            wishlist = Wishlist.objects.get(user=request.user)
            wishlist_count = WishlistItem.objects.filter(wishlist=wishlist).count()
        except Wishlist.DoesNotExist:
            wishlist_count = 0
    else:
        # For guest users
        session_wishlist = request.session.get('wishlist', [])
        wishlist_count = len(session_wishlist)
    
    return {'wishlist_count': wishlist_count}