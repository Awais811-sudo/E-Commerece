# signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Cart, Wishlist

@receiver(post_save, sender=User)
def create_user_cart_wishlist(sender, instance, created, **kwargs):
    if created:
        Cart.objects.create(user=instance)
        Wishlist.objects.create(user=instance)