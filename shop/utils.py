from decimal import Decimal
from .models import Cart

def calculate_total(cart_items):
    return sum(
        item.product.price * item.quantity
        for item in cart_items
        if item.product and item.product.price
    )