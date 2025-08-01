from django.db import models
from django.utils.text import slugify
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
import uuid
from django.db.models import Count, Q, F, ExpressionWrapper, IntegerField, Avg
from django.core.exceptions import ValidationError

User = settings.AUTH_USER_MODEL 

class Address(models.Model):
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    street = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    slug = models.SlugField(unique=True, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(f"{self.full_name}-{self.street}")
            unique_suffix = uuid.uuid4().hex[:8]
            self.slug = f"{base_slug}-{unique_suffix}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} - {self.street}, {self.city}, {self.country}"

class Order(models.Model):
    STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled')
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    delivery_address = models.ForeignKey(
        Address, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="orders"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    status_changes = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='processing'
    )

    def __str__(self):
        return f"Order #{self.id} - {self.get_status_display()}"
    

    

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)  # Made blank=True to allow manual entry
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    
    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:  # Only generate slug if not manually provided
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

class Tag(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True, blank=True)  # Made blank=True to allow manual entry

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:  # Only generate slug if not manually provided
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True, null=True)
    logo = models.ImageField(upload_to='brands/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)  # Allow manual entry if needed
    description = models.TextField()
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    discount_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True
    )
    category = models.ForeignKey(
        Category, 
        on_delete=models.CASCADE,
        related_name='products'
    )
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name='products', null=True, blank=True)
    tags = models.ManyToManyField(Tag, blank=True)
    stock = models.PositiveIntegerField()
    available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    featured = models.BooleanField(default=False)
    sold = models.PositiveIntegerField(default=0)
    weight = models.CharField(max_length=20, blank=True)
    views = models.PositiveIntegerField(default=0)
    view_count = models.PositiveIntegerField(default=0)
    last_sold = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:  # Auto-generate slug if not provided
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def average_rating(self):
        avg = self.reviews.aggregate(avg_rating=Avg('rating'))['avg_rating']
        return avg or 0.0

    @property
    def review_count(self):
        return self.reviews.count()

    @classmethod
    def get_trending_products(cls):
        thirty_days_ago = timezone.now() - timedelta(days=30)
        return cls.objects.annotate(
            recent_sales=Count('order_items', filter=Q(order_items__order__created_at__gte=thirty_days_ago)),
            total_score=ExpressionWrapper(F('view_count') + F('recent_sales'), output_field=IntegerField())
        ).order_by('-total_score')[:10]

    def get_similar_products(self):
        similar_by_tags = Product.objects.filter(
            tags__in=self.tags.all()
        ).exclude(id=self.id).distinct()
        similar_by_name = Product.objects.filter(
            Q(name__icontains=self.name) | Q(description__icontains=self.name)
        ).exclude(id=self.id).distinct()
        return (similar_by_tags | similar_by_name).distinct()

    def get_related_products(self):
        # Collaborative filtering: find users who ordered this product, then get other products they bought.
        collaborative = Product.objects.filter(
            order_items__order__user__in=User.objects.filter(
                order_items__product=self
            ).distinct()
        ).exclude(id=self.id).distinct()
        
        # Merge content-based and collaborative approaches
        content_based = self.get_similar_products()
        return (content_based | collaborative).distinct()[:6]

    @property
    def discount_percentage(self):
        if self.discount_price:
            return int(((self.price - self.discount_price) / self.price) * 100)
        return 0

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/')
    alt_text = models.CharField(max_length=200, blank=True, null=True)
    is_main = models.BooleanField(default=False)

    def clean(self):
        # Only run this check if the product has been saved.
        if not self.product_id:
            return

        if self.is_main:
            qs = ProductImage.objects.filter(product=self.product, is_main=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError("Only one main image is allowed per product.")

    def __str__(self):
        return f"{self.product.name} Image"

class ProductVariant(models.Model):
    """
    This model stores different variants of a product.
    You can add attributes such as wattage, color, shape, size, etc.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    wattage = models.PositiveIntegerField(blank=True, null=True)
    color = models.CharField(max_length=50, blank=True, null=True)
    shape = models.CharField(max_length=50, blank=True, null=True)
    size = models.CharField(max_length=50, blank=True, null=True)
    additional_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stock = models.PositiveIntegerField(default=0)

    def __str__(self):
        details = []
        if self.wattage:
            details.append(f"{self.wattage}W")
        if self.color:
            details.append(self.color)
        if self.shape:
            details.append(self.shape)
        if self.size:
            details.append(self.size)
        return f"{self.product.name} Variant: {' - '.join(details)}"

    
class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name='order_items', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, null=True, blank=True)

class Review(models.Model):
    product = models.ForeignKey(Product, related_name='reviews', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(choices=((1,1), (2,2), (3,3), (4,4), (5,5)))
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        ordering = ['-created_at']
        unique_together = ['product', 'user'] 

 # or use get_user_model() if preferred

# --- Wishlist Models ---

class Wishlist(models.Model):
    # We use a OneToOneField so that an authenticated user has exactly one wishlist.
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wishlist')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Wishlist for {self.user.username}"

class WishlistItem(models.Model):
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name='wishlistitem')
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)
    priority = models.PositiveIntegerField(
        default=1,
        help_text="Lower numbers indicate higher priority."
    )
    notes = models.TextField(
        blank=True, 
        null=True, 
        help_text="Optional notes for this wishlist item."
    )

    @property
    def tags(self):
        return self.product.tags.all()

    def __str__(self):
        # When a WishlistItem exists, we assume it belongs to an authenticated user.
        return f"{self.product.name} in {self.wishlist.user.username}'s wishlist"

# --- Cart Models ---
class Cart(models.Model):
    # For authenticated users, store the cart against the user.
    # For guest users, store a session key.
    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.CASCADE, related_name='cart'
    )
    session_key = models.CharField(max_length=40, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.user:
            return f"Cart for {self.user.username}"
        return f"Cart for session {self.session_key}"

    def get_total(self):
        # Sum all items’ subtotals in this cart.
        total = sum(item.get_subtotal() for item in self.items.all())
        return total

class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name='items'
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True)
    def get_subtotal(self):
        if self.product.discount_price:
            return self.product.discount_price * self.quantity
        return self.product.price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"
