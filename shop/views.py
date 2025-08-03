from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Case, When, F, DecimalField, Q, Sum, Count
from .models import *
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from .forms import CustomUserCreationForm, CustomAuthenticationForm, AddressForm
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import logging
from .utils import calculate_total  # Add this import
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import transaction
from django.forms.models import model_to_dict  # Add this import
import json
from django.views import View
from django.contrib.auth import get_user_model
from decimal import Decimal
User = get_user_model()

def search_view(request):
    query = request.GET.get('q', '')
    results = Product.objects.filter(
        Q(name__icontains=query) |
        Q(description__icontains=query) |
        Q(category__name__icontains=query) |
        Q(tags__name__icontains=query)
    ).distinct()
    
    # Get similar products if no results
    similar_products = None
    if not results.exists():
        similar_products = Product.objects.filter(
            category__name__icontains=query
        )[:5]
    
    return render(request, 'search_results.html', {
        'results': results,
        'query': query,
        'similar_products': similar_products
    })

def autocomplete(request):
    query = request.GET.get('term', '')
    suggestions = Product.objects.filter(
        Q(name__istartswith=query)
    ).values_list('name', flat=True)[:5]
    return JsonResponse(list(suggestions), safe=False)




class CheckoutView(View):
    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        default_address = Address.objects.filter(user=user, is_default=True).first() if user else None
        
        # For logged in, prefill the form; for guest, show an empty form.
        form = AddressForm(instance=default_address)
        
        # Retrieve cart: use user if available, else use session_key.
        if user:
            cart = Cart.objects.filter(user=user).first()
        else:
            session_key = request.session.session_key
            if not session_key:
                request.session.create()
                session_key = request.session.session_key
            cart = Cart.objects.filter(session_key=session_key).first()
        cart_items = CartItem.objects.filter(cart=cart) if cart else []
        total = sum(item.get_subtotal() for item in cart_items)
        
        return render(request, 'checkout.html', {
            'form': form,
            'cart_items': cart_items,
            'total': total,
            'default_address': default_address
        })

    def post(self, request):
        user = request.user if request.user.is_authenticated else None
        save_address = request.POST.get("save_address")  # Checkbox input

        # manually extract all fields
        full_name = request.POST.get('full_name')
        email = request.POST.get('email')
        street = request.POST.get('street')
        city = request.POST.get('city')
        state = request.POST.get('state')
        postal_code = request.POST.get('postal_code')
        country = request.POST.get('country')
        phone = request.POST.get('phone')

        # create address object
        address = Address(
            full_name=full_name,
            email=email,
            street=street,
            city=city,
            state=state,
            postal_code=postal_code,
            country=country,
            phone=phone
        )

        # If user is logged in & wants to save address
        if user and save_address:
            address.user = user
            # check for existing duplicate
            existing_address = Address.objects.filter(
                user=user,
                full_name=full_name,
                phone=phone,
                street=street,
                city=city,
                state=state,
                postal_code=postal_code,
                country=country
            ).first()
            if existing_address:
                address = existing_address
            else:
                address.save()
        else:
            # Guest or non-saving case
            address.save()

        # Retrieve cart
        if user:
            cart = Cart.objects.filter(user=user).first()
        else:
            session_key = request.session.session_key
            if not session_key:
                request.session.create()
                session_key = request.session.session_key
            cart = Cart.objects.filter(session_key=session_key).first()

        cart_items = CartItem.objects.filter(cart=cart) if cart else []
        total = sum(item.get_subtotal() for item in cart_items)

        if not cart_items:
            messages.error(request, "Your cart is empty!")
            return redirect('cart')

        # create order
        order = Order.objects.create(
            user=user,
            delivery_address=address,
            total=total,
            status='processing',
        )

        for cart_item in cart_items:
            product = cart_item.product
            quantity = cart_item.quantity

            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                price=product.price
            )

            product.sold += quantity
            product.stock = max(product.stock - quantity, 0)
            product.last_sold = timezone.now()
            product.save()

            if hasattr(cart_item, 'variant') and cart_item.variant:
                cart_item.variant.stock = max(cart_item.variant.stock - quantity, 0)
                cart_item.variant.save()

        cart_items.delete()
        messages.success(request, "Your order has been placed successfully!")
        return redirect('order_confirmation', order_id=order.id)







class OrderConfirmationView(View):
    """Handles order confirmation display."""
    def get(self, request, order_id):
        if request.user.is_authenticated:
            order = get_object_or_404(Order, id=order_id, user=request.user)
        else:
            order = get_object_or_404(Order, id=order_id)
            if request.session.get('guest_order_id') != order_id:
                return redirect('home')
        return render(request, 'order_confirmation.html', {'order': order})
    
class OrderDetailView(View):
    """Displays order details for the logged-in user only."""
    def get(self, request, order_id):
        if not request.user.is_authenticated:
            return redirect('login')  # Redirect non-logged-in users to login

        order = get_object_or_404(Order, id=order_id, user=request.user)  # Ensure order belongs to user
        
        return render(request, 'order_detail.html', {'order': order})
    
class OrderHistoryView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('login')

        delivered_orders = Order.objects.filter(user=request.user, status='delivered')
        return render(request, 'order_history.html', {'delivered_orders': delivered_orders})


class ProfileView(View):
    def get(self, request):
        user = request.user
        addresses = Address.objects.filter(user=user)
        orders = Order.objects.filter(user=user).order_by('-created_at')
        
        active_orders = orders.exclude(status__in=['delivered', 'cancelled'])
        delivered_orders = orders.filter(status='delivered')
        
        form = AddressForm()  # For adding new address

        return render(request, 'profile.html', {
            'user': user,
            'addresses': addresses,
            'active_orders': active_orders,
            'delivered_orders': delivered_orders,
            'form': form
        })

    def post(self, request):
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            messages.success(request, "Address added successfully!")
            return redirect('profile')

        messages.error(request, "There was an error with the address form.")
        return self.get(request)


@login_required
def logout_view(request):
    """Logs out the user and redirects to home."""
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('home')  # Redirect to homepage


def signup(request):
    if request.user.is_authenticated:
        return redirect('profile')
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('profile')
    else:
        form = CustomUserCreationForm()
    return render(request, 'signup.html', {'form': form})

def user_login(request):
    if request.user.is_authenticated:
        return redirect('profile')
    if request.method == 'POST':
        form = CustomAuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('profile')
    else:
        form = CustomAuthenticationForm()
    return render(request, 'login.html', {'form': form})

def user_logout(request):
    logout(request)
    return redirect('home')


@login_required
def edit_profile(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")

        # Updating user data
        user = request.user
        user.username = username
        user.email = email
        user.save()

        messages.success(request, "Profile updated successfully!")
        return redirect("edit_profile")  # Redirect back to the form after saving

    return render(request, "edit_profile.html")


@login_required
def manage_address(request, address_id=None):
    # Fetch existing address or create a new one
    address = Address.objects.filter(id=address_id, user=request.user).first() if address_id else None

    if request.method == 'POST':
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user  # Assign logged-in user

            # Prefill email and full name from user (if not provided)
            if not address.full_name:
                address.full_name = request.user.get_full_name()
            if not address.email:
                address.email = request.user.email

            # Ensure only one default address
            if address.is_default:
                Address.objects.filter(user=request.user).update(is_default=False)

            address.save()
            return redirect('profile')
    else:
        # Prefill the form with user's name and email if it's a new address
        initial_data = {'full_name': request.user.get_full_name(), 'email': request.user.email}
        form = AddressForm(instance=address, initial=initial_data)

    return render(request, 'manage_address.html', {'form': form})




def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug)
    
    # Track product views...
    viewed_products = request.session.get('viewed_products', [])
    if slug not in viewed_products:
        product.views += 1
        product.save()
        viewed_products.append(slug)
        request.session['viewed_products'] = viewed_products

    images = product.images.all()
    main_image = product.images.filter(is_main=True).first() or images.first()
    related_products = Product.objects.filter(category=product.category).exclude(id=product.id)[:4]

    # Collect variant data and convert Decimal to float
    variants = product.variants.all()
    variants_data = []
    for variant in variants:
        variants_data.append({
            'id': variant.id,
            'wattage': variant.wattage,
            'color': variant.color,
            'shape': variant.shape,
            'size': variant.size,
            'additional_price': float(variant.additional_price) if variant.additional_price is not None else None,
            'stock': variant.stock,
        })

    context = {
        'product': product,
        'images': images,
        'main_image': main_image,
        'recommended_products': related_products,
        'variants_data': json.dumps(variants_data),  # Now JSON serializable
        'wattages': list(variants.exclude(wattage__isnull=True).values_list('wattage', flat=True).distinct()),
        'colors': list(variants.exclude(color__exact="").values_list('color', flat=True).distinct()),
        'shapes': list(variants.exclude(shape__exact="").values_list('shape', flat=True).distinct()),
        'sizes': list(variants.exclude(size__exact="").values_list('size', flat=True).distinct()),
    }
    return render(request, 'product_detail.html', context)





def add_review(request, slug):
    if request.method == 'POST':
        product = get_object_or_404(Product, slug=slug)
        Review.objects.create(
            product=product,
            user=request.user,
            rating=request.POST.get('rating'),
            comment=request.POST.get('comment')
        )
        return redirect('product_detail', slug=slug)


def shop(request):
    # Annotate products with effective price (discount or regular)
    products = Product.objects.filter(available=True).annotate(
        effective_price=Case(
            When(discount_price__isnull=False, then=F('discount_price')),
            default=F('price'),
            output_field=DecimalField()
        )
    )

    # Filters
    price_min = request.GET.get('price_min')
    price_max = request.GET.get('price_max')
    category = request.GET.get('category')
    sort_by = request.GET.get('sort_by')
    brand_slug = request.GET.get('brand')
    if brand_slug:
        products = products.filter(brand__slug=brand_slug)
    # Price filter using effective price
    if price_min and price_max:
        products = products.filter(
            effective_price__gte=price_min,
            effective_price__lte=price_max
        )

    # Category filter
    if category:
        products = products.filter(category__slug=category)

    # Sorting options
    if sort_by == 'price_low_to_high':
        products = products.order_by('effective_price')
    elif sort_by == 'price_high_to_low':
        products = products.order_by('-effective_price')
    elif sort_by == 'newest_first':
        products = products.order_by('-created_at')

    # Pagination
    paginator = Paginator(products, 40)  # 40 products per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get all categories for sidebar
    categories = Category.objects.all()
    brands = Brand.objects.all()
    context = {
        'page_obj': page_obj,
        'categories': categories,
        'current_filters': {
            'brands': brands,
            'price_min': price_min,
            'price_max': price_max,
            'category': category,
            'sort_by': sort_by
        }
    }
    return render(request, 'shop.html', context)





logger = logging.getLogger(__name__)

def get_cart(request):
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
    else:
        session_key = request.session.session_key
        if not session_key:
            request.session.create()
            session_key = request.session.session_key
        cart, _ = Cart.objects.get_or_create(session_key=session_key)
    return cart

def home(request):
    wishlist_items = None
    cart_items = None
    if request.user.is_authenticated:
        # Assuming a wishlist model exists; adjust as needed
        wishlist = getattr(request.user, 'wishlist', None)
        if wishlist:
            wishlist_items = wishlist.wishlistitem.all()
        cart = get_cart(request)
        if cart:
            cart_items = cart.items.all()
    
    context = {
        'wishlist_items': wishlist_items,
        'cart_items': cart_items,
        'popular_products': Product.objects.filter(featured=True)[:8],
        'categories': Category.objects.all()[:6],
        'new_arrivals': Product.objects.order_by('-created_at')[:8],
    }
    return render(request, 'home.html', context)

def category_view(request, slug):
    category = get_object_or_404(Category, slug=slug)
    products = Product.objects.filter(category=category)

    context = {
        'category': category,
        'products': products,
        'categories': Category.objects.all()  # if you want sidebar filters
    }
    return render(request, 'category.html', context)

@require_POST
def add_to_cart(request, product_id):
    try:
        cart = get_cart(request)
        product = get_object_or_404(Product, id=product_id)
        variant_id = request.POST.get('variant_id')  # Assuming variant is passed in POST
        variant = ProductVariant.objects.filter(id=variant_id).first() if variant_id else None
        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product, variant=variant)
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()

        cart_items = CartItem.objects.filter(cart=cart)
        cart_count = sum(item.quantity for item in cart_items)

        return JsonResponse({
            'success': True,
            'cart_count': cart_count,
        })
    except Exception as e:
        logger.error("Error adding to cart: %s", str(e))
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@require_POST
def update_cart(request, product_id, action):
    try:
        cart = get_cart(request)
        product = get_object_or_404(Product, id=product_id)
        cart_item = CartItem.objects.filter(cart=cart, product=product).first()
        
        if not cart_item:
            return JsonResponse({'success': False, 'error': 'Item not found in cart'}, status=404)
        
        with transaction.atomic():
            if action == 'increase':
                cart_item.quantity += 1
                cart_item.save()
            elif action == 'decrease':
                if cart_item.quantity > 1:
                    cart_item.quantity -= 1
                    cart_item.save()
                else:
                    cart_item.delete()
            elif action == 'remove':
                cart_item.delete()
        
        cart.refresh_from_db()
        cart_items = CartItem.objects.filter(cart=cart)
        total = sum(item.get_subtotal() for item in cart_items)
        cart_count = sum(item.quantity for item in cart_items)
        
        updated_item = CartItem.objects.filter(cart=cart, product=product).first()
        
        return JsonResponse({
            'success': True,
            'quantity': updated_item.quantity if updated_item else 0,
            'subtotal': float(updated_item.get_subtotal()) if updated_item else 0,
            'total': float(total),
            'cart_count': cart_count,
            'removed': not updated_item
        })
    except Exception as e:
        logger.error("Cart update error: %s", e, exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def cart(request):
    cart = get_cart(request)
    cart_items = CartItem.objects.filter(cart=cart).select_related('product', 'variant')
    total = 0
    for item in cart_items:
        item.subtotal = item.get_subtotal()
        total += item.subtotal

    recommended_products = Product.objects.order_by('-created_at')[:6]  # Simplified for example

    return render(request, 'cart.html', {
        'cart_items': cart_items,
        'total': total,
        'recommended_products': recommended_products,
    })
@require_http_methods(["DELETE"])
def remove_from_cart(request, item_id):
    """
    Remove a cart item from the cart.
    
    For authenticated users:
      - The cart is associated with the user.
      - The item is looked up using the user.
      
    For guest users:
      - The cart is associated with the session key.
      - The item is removed from that guest cart.
    """
    # Retrieve the cart (this function handles both authenticated and guest cases)
    cart = get_cart(request)
    
    try:
        # For authenticated users, enforce that the cart item belongs to the user's cart.
        if request.user.is_authenticated:
            cart_item = CartItem.objects.get(id=item_id, cart__user=request.user)
        else:
            cart_item = CartItem.objects.get(id=item_id, cart=cart)
        
        cart_item.delete()
        
        # After deletion, recalculate the cart total.
        total = float(cart.get_total())
        return JsonResponse({
            'success': True,
            'total': total,
            'message': 'Item removed from cart.'
        })
    
    except CartItem.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Cart item not found.'
        }, status=404)

def get_user_wishlist(user):
    """Retrieve or create a wishlist for the authenticated user."""
    wishlist_obj, _ = Wishlist.objects.get_or_create(user=user)
    return wishlist_obj

def wishlist(request):
    """
    Retrieve wishlist items for authenticated users and session-stored products for guests.
    """
    if request.user.is_authenticated:
        wishlist_obj = get_user_wishlist(request.user)
        wishlist_items = wishlist_obj.wishlistitem.select_related('product').all()
        is_guest = False
    else:
        session_wishlist = request.session.get('wishlist', [])
        wishlist_items = Product.objects.filter(id__in=session_wishlist) if session_wishlist else []
        is_guest = True

    context = {
        'wishlist_items': wishlist_items,
        'is_guest': is_guest,
    }
    return render(request, 'wishlist.html', context)

def add_to_wishlist(request, product_id):
    """
    Adds product to wishlist for both authenticated and guest users.
    """
    if request.user.is_authenticated:
        wishlist_obj = get_user_wishlist(request.user)
        WishlistItem.objects.get_or_create(wishlist=wishlist_obj, product_id=product_id)
    else:
        wishlist = request.session.get('wishlist', [])
        if product_id not in wishlist:
            wishlist.append(product_id)
            request.session['wishlist'] = wishlist  # Save to session

    wishlist_count = len(request.session.get('wishlist', [])) if not request.user.is_authenticated else WishlistItem.objects.filter(wishlist__user=request.user).count()

    return JsonResponse({'success': True, 'wishlist_count': wishlist_count})


@require_http_methods(["DELETE"])
def delete_wishlist_item(request, item_id):
    """
    Deletes a wishlist item.
    For authenticated users: delete the WishlistItem instance.
    For guest users: remove the product ID from the session.
    """
    if request.user.is_authenticated:
        try:
            item = WishlistItem.objects.get(id=item_id, wishlist__user=request.user)
            item.delete()
            return JsonResponse({'success': True})
        except WishlistItem.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Item not found.'}, status=404)
    else:
        wishlist = request.session.get('wishlist', [])
        try:
            product_id = int(item_id)
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid item id.'}, status=400)
        if product_id in wishlist:
            wishlist.remove(product_id)
            request.session['wishlist'] = wishlist
        return JsonResponse({'success': True})
    

# <----------- DASHBOARD --------------->

from django.shortcuts import render

def admin_dashboard(request):
    # Get date range from query params (default to 30 days)
    days = int(request.GET.get('days', 30))
    date_range = timezone.now() - timedelta(days=days)
    
    # Previous period for comparison
    prev_date_range = timezone.now() - timedelta(days=days*2)
    
    # Orders data
    orders = Order.objects.filter(created_at__gte=date_range)
    orders_count = orders.count()
    prev_orders = Order.objects.filter(
        created_at__gte=prev_date_range, 
        created_at__lt=date_range
    ).count()
    orders_change = ((orders_count - prev_orders) / prev_orders * 100) if prev_orders else 0
    
    # Sales data
    total_sales = orders.aggregate(total=Sum('total'))['total'] or Decimal('0')
    prev_sales = Order.objects.filter(
        created_at__gte=prev_date_range, 
        created_at__lt=date_range
    ).aggregate(total=Sum('total'))['total'] or Decimal('0')
    sales_change = ((total_sales - prev_sales) / prev_sales * Decimal('100')) if prev_sales else Decimal('0')
    
    # Revenue (assuming revenue is 85% of sales)
    revenue = total_sales * Decimal('0.85')
    prev_revenue = prev_sales * Decimal('0.85')
    revenue_change = ((revenue - prev_revenue) / prev_revenue * Decimal('100')) if prev_revenue else Decimal('0')
    
    # Customers data
    new_customers = User.objects.filter(date_joined__gte=date_range).count()
    prev_customers = User.objects.filter(
        date_joined__gte=prev_date_range, 
        date_joined__lt=date_range
    ).count()
    customers_change = ((new_customers - prev_customers) / prev_customers * 100) if prev_customers else 0
    
    # Top products
    top_products = Product.objects.annotate(
        order_count=Count('order_items', filter=Q(order_items__order__created_at__gte=date_range))
    ).order_by('-order_count')[:5]
    
    # Recent orders
    recent_orders = orders.order_by('-created_at')[:5]
    
    # New customers list
    new_customers_list = User.objects.filter(date_joined__gte=date_range).order_by('-date_joined')[:5]
    
    # In the chart data section of your view
    # Chart data - weekly
    weekly_labels = []
    weekly_data = []
    for i in range(7, 0, -1):
        day = timezone.now() - timedelta(days=i)
        weekly_labels.append(day.strftime('%a'))
        day_sales = Order.objects.filter(
            created_at__date=day.date()
        ).aggregate(total=Sum('total'))['total'] or Decimal('0')
        weekly_data.append(float(day_sales))  # Convert Decimal to float for Chart.js

    # Chart data - monthly
    monthly_labels = []
    monthly_data = []
    for i in range(12, 0, -1):
        month = timezone.now() - timedelta(days=30*i)
        monthly_labels.append(month.strftime('%b'))
        month_sales = Order.objects.filter(
            created_at__month=month.month,
            created_at__year=month.year
        ).aggregate(total=Sum('total'))['total'] or Decimal('0')
        monthly_data.append(float(month_sales))  # Convert Decimal to float for Chart.js
    
    context = {
        'installed_apps': [app.split('.')[-1] for app in settings.INSTALLED_APPS],
        'orders_count': orders_count,
        'orders_change': orders_change,
        'total_sales': total_sales,
        'sales_change': sales_change,
        'revenue': revenue,
        'revenue_change': revenue_change,
        'new_customers': new_customers,
        'customers_change': customers_change,
        'top_products': top_products,
        'recent_orders': recent_orders,
        'new_customers_list': new_customers_list,
        'weekly_labels': weekly_labels,
        'weekly_data': weekly_data,
        'monthly_labels': monthly_labels,
        'monthly_data': monthly_data,
        'now': timezone.now(),
    }
    
    return render(request, 'dashboard/dashboard.html', context)





def order_list(request):
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('search', '')
    
    # Base queryset
    orders = Order.objects.select_related(
        'user',
        'delivery_address'
    ).prefetch_related(
        'items',
        'items__product',
        'items__product__images',
        'items__variant'
    ).order_by('-created_at')
    
    # Apply filters
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    if search_query:
        orders = orders.filter(
            Q(id__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(delivery_address__full_name__icontains=search_query) |
            Q(delivery_address__phone__icontains=search_query)
        )
    
    return render(request, 'dashboard/orders.html', {
        'orders': orders,
        'status_filter': status_filter,
        'search_query': search_query,
        'status_choices': Order.STATUS_CHOICES,
    })



def update_order_status(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id)
        new_status = request.POST.get('status')
        if new_status in dict(Order.STATUS_CHOICES):
            order.status = new_status
            order.save()
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Invalid status'})
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

def cancel_order(request, order_id):
    if request.method == 'POST':
        order = Order.objects.get(id=order_id)
        order.status = 'cancelled'
        order.save()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'message': 'Invalid request'})
