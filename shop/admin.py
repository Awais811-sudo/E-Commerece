from django.contrib import admin
from .models import Category, Tag, Product
from django.contrib import admin
from .models import Order, OrderItem, Address, ProductImage, ProductVariant, Brand
from django.utils.html import format_html



@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    search_fields = ('full_name', 'street', 'city', 'phone', 'user__email')
    list_filter = ('city', 'country', 'is_default')
    list_display = ('full_name', 'city', 'country', 'phone', 'user')
    autocomplete_fields = ('user',)
    list_select_related = ('user',)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'price', 'subtotal_display')
    can_delete = False

    def subtotal_display(self, obj):
        if obj.price is None or obj.quantity is None:
            return "N/A"
        return obj.price * obj.quantity
    subtotal_display.short_description = "Subtotal"


class CityFilter(admin.SimpleListFilter):
    title = 'City'
    parameter_name = 'city'

    def lookups(self, request, model_admin):
        cities = Address.objects.order_by('city').values_list('city', flat=True).distinct()
        return [(city, city) for city in cities if city]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(delivery_address__city=self.value())
        return queryset


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]
    list_display = (
        'id', 'user_info', 'status', 'total', 'created_at',
        'delivery_address_info', 'get_products'
    )
    list_editable = ('status',)
    list_filter = ('status', 'created_at')
    search_fields = (
        'delivery_address__full_name',
        'delivery_address__phone',
        'delivery_address__email',
        'user__email',
        'id',
        'items__product__name'
    )
    date_hierarchy = 'created_at'
    raw_id_fields = ('delivery_address', 'user')
    autocomplete_fields = ('delivery_address', 'user')

    fieldsets = (
        (None, {'fields': ('user', 'status', 'total')}),
        ('Shipping Address', {'fields': ('delivery_address',)}),
    )

    def user_info(self, obj):
        if obj.user:
            name = obj.user.get_full_name() or obj.user.username
            return f"{name} ({obj.user.email})"
        if obj.delivery_address:
            return f"Guest: {obj.delivery_address.full_name}"
        return "Guest"
    user_info.short_description = 'Customer'

    def delivery_address_info(self, obj):
        addr = obj.delivery_address
        if addr:
            return format_html(
                "<strong>{}</strong><br>{}<br>{}, {} {}<br>Phone: {}<br>Email: {}",
                addr.full_name,
                addr.street,
                addr.city,
                addr.state,
                addr.postal_code,
                addr.phone,
                addr.email
            )
        return "No address"
    delivery_address_info.short_description = 'Shipping Address'

    def get_products(self, obj):
        items = obj.items.all()
        if items.exists():
            return ", ".join([f"{item.product.name} (x{item.quantity})" for item in items])
        return "No products"
    get_products.short_description = "Products Ordered"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('delivery_address', 'user')





class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'image')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'description')

admin.site.register(Category, CategoryAdmin)

class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)

admin.site.register(Tag, TagAdmin)


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1 

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        # Optional: add custom validation to ensure only one image is marked as main per product.
        return formset
      
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'category', 'available', 'featured')
    list_filter = ('category', 'available', 'featured', 'tags')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'description')
    filter_horizontal = ('tags',)
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'slug', 'description')
        }),
        ('Pricing & Inventory', {
            'fields': ('price', 'discount_price', 'stock', 'available')
        }),
        ('Categorization', {
            'fields': ('category', 'tags', 'featured')
        }),
        # Removed the 'Media' section since 'image' field no longer exists.
    )
    inlines = [ProductImageInline, ProductVariantInline]

admin.site.register(Product, ProductAdmin)

admin.site.register(Brand)
