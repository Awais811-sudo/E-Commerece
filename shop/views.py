from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Case, When, F, DecimalField, Q, Sum, Count, Prefetch, Avg
from .models import *
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from .forms import CustomUserCreationForm, CustomAuthenticationForm, AddressForm
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import logging
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import transaction
from django.forms.models import model_to_dict
import json
from django.views import View
from django.contrib.auth import get_user_model
from decimal import Decimal
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from django.db import IntegrityError
from django.views.decorators.http import require_GET

User = get_user_model()

logger = logging.getLogger(__name__)

# ========== UTILITY FUNCTIONS ==========
def get_cart(request):
    """Get or create cart for user or session"""
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
    else:
        session_key = request.session.session_key
        if not session_key:
            request.session.create()
            session_key = request.session.session_key
        cart, _ = Cart.objects.get_or_create(session_key=session_key)
    return cart

def get_cart_count(request):
    """Get cart item count for the current user/session"""
    cart = get_cart(request)
    cart_items = CartItem.objects.filter(cart=cart)
    return sum(item.quantity for item in cart_items)

def get_wishlist_count(request):
    """Get wishlist item count for the current user/session"""
    if request.user.is_authenticated:
        try:
            wishlist = Wishlist.objects.get(user=request.user)
            return WishlistItem.objects.filter(wishlist=wishlist).count()
        except Wishlist.DoesNotExist:
            return 0
    else:
        # For guest users, check session
        session_wishlist = request.session.get('wishlist', [])
        return len(session_wishlist)

def get_user_wishlist(user):
    """Get or create wishlist for user"""
    wishlist_obj, _ = Wishlist.objects.get_or_create(user=user)
    return wishlist_obj

# ========== CONTEXT PROCESSORS ==========
def cart_count(request):
    """Returns the number of items in the user's cart."""
    return {'cart_count': get_cart_count(request)}

def wishlist_count_processor(request):
    """Returns the number of items in the user's wishlist."""
    return {'wishlist_count': get_wishlist_count(request)}

# ========== API ENDPOINTS ==========
# shop/views.py - Update the header_counts_api function

@require_GET
@csrf_exempt
def header_counts_api(request):
    """API endpoint to get cart and wishlist counts for the header"""
    try:
        # Initialize counts
        cart_count = 0
        wishlist_count = 0
        
        # Get cart count
        if request.user.is_authenticated:
            # For logged-in users
            try:
                cart = Cart.objects.get(user=request.user)
                cart_items = CartItem.objects.filter(cart=cart)
                cart_count = sum(item.quantity for item in cart_items)
            except Cart.DoesNotExist:
                cart_count = 0
            
            # Get wishlist count for logged-in users
            try:
                wishlist = Wishlist.objects.get(user=request.user)
                wishlist_count = WishlistItem.objects.filter(wishlist=wishlist).count()
            except Wishlist.DoesNotExist:
                wishlist_count = 0
        else:
            # For guest users - use session
            session_key = request.session.session_key
            
            # Ensure session exists
            if not session_key:
                request.session.create()
                session_key = request.session.session_key
                request.session.save()
            
            # Get cart count from session cart
            try:
                cart = Cart.objects.get(session_key=session_key)
                cart_items = CartItem.objects.filter(cart=cart)
                cart_count = sum(item.quantity for item in cart_items)
            except Cart.DoesNotExist:
                cart_count = 0
            
            # Get wishlist count from session
            session_wishlist = request.session.get('wishlist', [])
            wishlist_count = len(session_wishlist)
        
        return JsonResponse({
            'success': True,
            'cart_count': cart_count,
            'wishlist_count': wishlist_count
        })
        
    except Exception as e:
        # Log the error
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in header_counts_api: {str(e)}")
        print(f"Traceback: {error_details}")
        
        # Return safe default values
        return JsonResponse({
            'success': False,
            'error': 'Internal server error',
            'cart_count': 0,
            'wishlist_count': 0
        }, status=500)
    
# ========== VIEWS ==========

def search_view(request):
    query = request.GET.get('q', '')
    results = Product.objects.filter(
        Q(name__icontains=query) |
        Q(description__icontains=query) |
        Q(category__name__icontains=query) |
        Q(tags__name__icontains=query)
    ).distinct()
    
    # Get wishlist product IDs for the current user
    wishlist_product_ids = []
    if request.user.is_authenticated:
        # For authenticated users
        wishlist_product_ids = WishlistItem.objects.filter(
            wishlist__user=request.user
        ).values_list('product_id', flat=True)
    else:
        # For guest users (from session)
        wishlist_product_ids = request.session.get('wishlist', [])
    
    similar_products = None
    if not results.exists():
        similar_products = Product.objects.filter(
            category__name__icontains=query
        )[:5]
    
    return render(request, 'search_results.html', {
        'results': results,
        'query': query,
        'similar_products': similar_products,
        'wishlist_product_ids': list(wishlist_product_ids)  # Convert to list
    })

def autocomplete(request):
    query = request.GET.get('term', '')
    suggestions = Product.objects.filter(
        Q(name__istartswith=query)
    ).values_list('name', flat=True)[:5]
    return JsonResponse(list(suggestions), safe=False)

@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Your password was successfully updated!')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'change_password.html', {
        'form': form,
        'title': 'Change Password'
    })

class CheckoutView(View):
    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        default_address = Address.objects.filter(user=user, is_default=True).first() if user else None
        
        form = AddressForm(instance=default_address)
        
        cart = get_cart(request)
        cart_items = CartItem.objects.filter(cart=cart).select_related('product', 'variant') if cart else []
        total = sum(item.get_subtotal() for item in cart_items)
        
        return render(request, 'checkout.html', {
            'form': form,
            'cart_items': cart_items,
            'total': total,
            'default_address': default_address
        })

    def post(self, request):
        print("\n=== CHECKOUT DEBUG START ===")
        print(f"User: {request.user if request.user.is_authenticated else 'Guest'}")
        
        user = request.user if request.user.is_authenticated else None
        save_address = request.POST.get("save_address")
        
        # Extract address fields
        full_name = request.POST.get('full_name')
        email = request.POST.get('email')
        street = request.POST.get('street')
        city = request.POST.get('city')
        state = request.POST.get('state')
        postal_code = request.POST.get('postal_code')
        country = request.POST.get('country')
        phone = request.POST.get('phone')
        
        # Debug address fields
        print(f"\nAddress fields:")
        print(f"Full Name: {full_name}")
        print(f"Email: {email}")
        print(f"Street: {street}")
        print(f"City: {city}")
        print(f"State: {state}")
        print(f"Postal Code: {postal_code}")
        print(f"Country: {country}")
        print(f"Phone: {phone}")
        
        # Validate required fields
        required_fields = ['full_name', 'email', 'street', 'city', 'state', 'postal_code', 'country', 'phone']
        missing_fields = [field for field in required_fields if not request.POST.get(field)]
        
        if missing_fields:
            print(f"\nERROR: Missing required fields: {missing_fields}")
            messages.error(request, f"Please fill in all required fields: {', '.join(missing_fields)}")
            return redirect('checkout')
        
        # Create address object
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
                print("Using existing address")
            else:
                address.save()
                print("Created new address")
        else:
            address.save()
            print("Created guest address")
        
        # Retrieve cart
        cart = get_cart(request)
        cart_items = CartItem.objects.filter(cart=cart).select_related('product', 'variant') if cart else []
        
        print(f"\nCart items count: {cart_items.count()}")
        
        if not cart_items:
            print("ERROR: Cart is empty")
            messages.error(request, "Your cart is empty!")
            return redirect('cart')
        
        try:
            # Calculate total from cart items
            order_total = Decimal('0')
            order_items_data = []
            
            for cart_item in cart_items:
                # Calculate prices for this item
                if cart_item.product.discount_price:
                    base_price = cart_item.product.discount_price
                else:
                    base_price = cart_item.product.price
                
                original_price = cart_item.product.price
                
                # Add variant additional price if exists
                if cart_item.variant and cart_item.variant.additional_price:
                    base_price += cart_item.variant.additional_price
                    original_price += cart_item.variant.additional_price
                
                # Calculate item total
                item_total = base_price * cart_item.quantity
                order_total += item_total
                
                print(f"  Cart item: {cart_item.product.name}")
                print(f"    Quantity: {cart_item.quantity}")
                print(f"    Price: {base_price}")
                print(f"    Item total: {item_total}")
                print(f"    Has variant: {bool(cart_item.variant)}")
                
                # Prepare order item data
                order_items_data.append({
                    'product': cart_item.product,
                    'variant': cart_item.variant,
                    'quantity': cart_item.quantity,
                    'price': original_price,
                    'discounted_price': base_price,
                    'product_obj': cart_item.product,  # For stock update
                    'variant_obj': cart_item.variant,  # For stock update
                })
            
            print(f"\nCalculated order total: {order_total}")
            
            # Create order with calculated total
            order = Order.objects.create(
                user=user,
                delivery_address=address,
                total=order_total,  # Use calculated total
                status='processing',
            )
            print(f"Order created: ID {order.id}")
            
            # Create order items
            for item_data in order_items_data:
                OrderItem.objects.create(
                    order=order,
                    product=item_data['product'],
                    variant=item_data['variant'],
                    quantity=item_data['quantity'],
                    price=item_data['price'],
                    discounted_price=item_data['discounted_price']
                )
                
                # Update product stock
                product = item_data['product_obj']
                product.sold += item_data['quantity']
                product.stock = max(product.stock - item_data['quantity'], 0)
                product.last_sold = timezone.now()
                product.save()
                
                # Update variant stock if exists
                if item_data['variant_obj']:
                    variant = item_data['variant_obj']
                    variant.stock = max(variant.stock - item_data['quantity'], 0)
                    variant.save()
            
            print(f"Created {len(order_items_data)} order items")
            
            # Clear cart
            cart_items.delete()
            print("Cart cleared")
            
            # Store order ID in session for guest users
            if not user:
                request.session['guest_order_id'] = order.id
                request.session.modified = True
                print(f"Guest order ID stored in session: {order.id}")
            
            print("=== CHECKOUT DEBUG END ===\n")
            
            messages.success(request, "Your order has been placed successfully!")
            return redirect('order_confirmation', order_id=order.id)
            
        except Exception as e:
            print(f"\nERROR during checkout: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Clean up: delete address if it was newly created
            if address and address.pk and not (user and save_address and 'existing_address' in locals()):
                try:
                    address.delete()
                    print("Cleaned up address")
                except:
                    pass
            
            messages.error(request, "An error occurred during checkout. Please try again.")
            return redirect('cart')

class OrderConfirmationView(View):
    def get(self, request, order_id):
        if request.user.is_authenticated:
            order = get_object_or_404(
                Order.objects.select_related('delivery_address')
                .prefetch_related(
                    Prefetch('items', queryset=OrderItem.objects.select_related('product', 'variant'))
                ),
                id=order_id, 
                user=request.user
            )
        else:
            order = get_object_or_404(
                Order.objects.select_related('delivery_address')
                .prefetch_related(
                    Prefetch('items', queryset=OrderItem.objects.select_related('product', 'variant'))
                ),
                id=order_id
            )
            if request.session.get('guest_order_id') != order_id:
                return redirect('home')
        return render(request, 'order_confirmation.html', {'order': order})

class OrderDetailView(View):
    def get(self, request, order_id):
        if not request.user.is_authenticated:
            return redirect('login')
        
        order = get_object_or_404(
            Order.objects.select_related('delivery_address')
            .prefetch_related(
                Prefetch('items', queryset=OrderItem.objects.select_related('product', 'variant'))
            ),
            id=order_id, 
            user=request.user
        )
        
        return render(request, 'order_detail.html', {'order': order})

class OrderHistoryView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('login')
        
        delivered_orders = Order.objects.filter(
            user=request.user, 
            status='delivered'
        ).select_related('delivery_address').order_by('-created_at')
        
        return render(request, 'order_history.html', {'delivered_orders': delivered_orders})

class ProfileView(View):
    def get(self, request):
        user = request.user
        addresses = Address.objects.filter(user=user)
        
        # Get orders with proper prefetching
        orders = Order.objects.filter(user=user).select_related('delivery_address').order_by('-created_at')
        
        active_orders = orders.exclude(status__in=['delivered', 'cancelled'])
        delivered_orders = orders.filter(status='delivered')
        
        form = AddressForm()
        
        return render(request, 'profile.html', {
            'user': user,
            'addresses': addresses,
            'active_orders': active_orders,
            'delivered_orders': delivered_orders,
            'form': form
        })
    
    def post(self, request):
        # Handle setting default address
        address_id = request.POST.get('set_default_address_id')
        if address_id:
            try:
                # Clear existing default
                Address.objects.filter(user=request.user, is_default=True).update(is_default=False)
                # Set new default
                address = Address.objects.get(id=address_id, user=request.user)
                address.is_default = True
                address.save()
                messages.success(request, "Default address updated successfully!")
            except Address.DoesNotExist:
                messages.error(request, "Address not found.")
        
        return redirect('profile')
    
@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('home')

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
        
        user = request.user
        user.username = username
        user.email = email
        user.save()
        
        messages.success(request, "Profile updated successfully!")
        return redirect("edit_profile")
    
    return render(request, "edit_profile.html")

class OrderHistoryView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Get delivered orders with related data
        delivered_orders = Order.objects.filter(
            user=request.user, 
            status='delivered'
        ).select_related('delivery_address').prefetch_related(
            Prefetch('items', queryset=OrderItem.objects.select_related('product', 'variant'))
        ).order_by('-created_at')
        
        # Get orders by status for filtering
        status_filter = request.GET.get('status', 'all')
        
        if status_filter == 'all':
            orders = Order.objects.filter(user=request.user)
        elif status_filter == 'active':
            orders = Order.objects.filter(
                user=request.user
            ).exclude(status__in=['delivered', 'cancelled'])
        elif status_filter == 'delivered':
            orders = Order.objects.filter(user=request.user, status='delivered')
        elif status_filter == 'cancelled':
            orders = Order.objects.filter(user=request.user, status='cancelled')
        else:
            orders = Order.objects.filter(user=request.user, status=status_filter)
        
        orders = orders.select_related('delivery_address').prefetch_related(
            Prefetch('items', queryset=OrderItem.objects.select_related('product', 'variant'))
        ).order_by('-created_at')
        
        # Add pagination
        paginator = Paginator(orders, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Statistics
        total_orders = Order.objects.filter(user=request.user).count()
        total_spent = Order.objects.filter(user=request.user).aggregate(
            total=Sum('total')
        )['total'] or 0
        
        return render(request, 'order_history.html', {
            'orders': page_obj,
            'delivered_orders': delivered_orders,
            'total_orders': total_orders,
            'total_spent': total_spent,
            'status_filter': status_filter,
            'status_choices': Order.STATUS_CHOICES,
        })


@login_required
def manage_address(request, address_id=None):
    address = Address.objects.filter(id=address_id, user=request.user).first() if address_id else None
    
    if request.method == 'POST':
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            
            # Only pre-fill email if it's empty
            if not address.email:
                address.email = request.user.email
            
            # If setting as default, update all other addresses
            if form.cleaned_data.get('is_default', False):
                Address.objects.filter(user=request.user).update(is_default=False)
            elif address_id and not form.cleaned_data.get('is_default', False):
                # If unchecking default for existing address, check if we need to set another as default
                if address.is_default:
                    # Find another address to set as default
                    other_address = Address.objects.filter(user=request.user).exclude(id=address_id).first()
                    if other_address:
                        other_address.is_default = True
                        other_address.save()
                    address.is_default = False
            
            address.save()
            messages.success(request, "Address saved successfully!")
            return redirect('profile')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        # Initial data for new addresses
        initial_data = {}
        if not address:
            initial_data = {
                'full_name': request.user.get_full_name(),
                'email': request.user.email
            }
        form = AddressForm(instance=address, initial=initial_data)
    
    # Get all addresses for the user to check limit
    addresses = Address.objects.filter(user=request.user)
    
    return render(request, 'manage_address.html', {
        'form': form, 
        'address': address,
        'addresses': addresses
    })


def delete_address(request, pk):
    address = Address.objects.get(id=pk, user=request.user)
    address.delete()
    return redirect('profile')

def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.prefetch_related('images', 'reviews__user'),
        slug=slug
    )
    
    # Check if user has already reviewed this product
    user_has_reviewed = False
    user_review = None
    
    if request.user.is_authenticated:
        user_review = Review.objects.filter(product=product, user=request.user).first()
        user_has_reviewed = user_review is not None
    
    # Get product variants
    variants = product.variants.all()
    
    # Group variants by type for template display
    wattages = variants.filter(wattage__isnull=False).distinct('wattage')
    colors = variants.filter(color__isnull=False).distinct('color')
    shapes = variants.filter(shape__isnull=False).distinct('shape')
    sizes = variants.filter(size__isnull=False).distinct('size')
    
    # Get recommended products (simplified logic - adjust as needed)
    recommended_products = Product.objects.filter(
        category=product.category
    ).exclude(id=product.id)[:4]
    
    context = {
        'product': product,
        'images': product.images.all(),
        'main_image': product.images.first(),
        'user_has_reviewed': user_has_reviewed,
        'user_review': user_review,
        'recommended_products': recommended_products,
        'wattages': wattages,
        'colors': colors,
        'shapes': shapes,
        'sizes': sizes,
        'variants': variants,
    }
    return render(request, 'product_detail.html', context)

@login_required
def add_review(request, slug):
    product = get_object_or_404(Product, slug=slug)
    
    # Check if user already reviewed this product
    existing_review = Review.objects.filter(product=product, user=request.user).first()
    
    if existing_review:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'You have already reviewed this product',
                'existing_review': {
                    'rating': existing_review.rating,
                    'comment': existing_review.comment,
                    'created_at': existing_review.created_at.strftime('%B %d, %Y')
                }
            }, status=400)
        messages.error(request, 'You have already reviewed this product.')
        return redirect('product_detail', slug=slug)
    
    if request.method == 'POST':
        rating = request.POST.get('rating')
        comment = request.POST.get('comment')
        
        if not rating or not comment:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'Rating and comment are required'
                }, status=400)
            messages.error(request, 'Rating and comment are required.')
            return redirect('product_detail', slug=slug)
        
        try:
            review = Review.objects.create(
                product=product,
                user=request.user,
                rating=rating,
                comment=comment
            )
            
            # Update product average rating
            product.average_rating = product.reviews.aggregate(Avg('rating'))['rating__avg']
            product.save()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Review submitted successfully',
                    'review': {
                        'user': request.user.username,
                        'rating': rating,
                        'comment': comment,
                        'created_at': review.created_at.strftime('%B %d, %Y')
                    }
                })
            
            messages.success(request, 'Review submitted successfully!')
            return redirect('product_detail', slug=slug)
            
        except IntegrityError:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'You have already reviewed this product'
                }, status=400)
            messages.error(request, 'You have already reviewed this product.')
            return redirect('product_detail', slug=slug)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': False,
            'error': 'Invalid request method'
        }, status=400)
    
    return redirect('product_detail', slug=slug)

def shop(request):
    # Get wishlist product IDs for the current user
    wishlist_product_ids = []
    if request.user.is_authenticated:
        try:
            wishlist = Wishlist.objects.get(user=request.user)
            wishlist_product_ids = list(wishlist.wishlistitem.values_list('product_id', flat=True))
        except Wishlist.DoesNotExist:
            pass
    else:
        session_wishlist = request.session.get('wishlist', [])
        wishlist_product_ids = [int(pid) for pid in session_wishlist if str(pid).isdigit()]
    
    # Get products with filtering
    products = Product.objects.filter(available=True).annotate(
        effective_price=Case(
            When(discount_price__isnull=False, then=F('discount_price')),
            default=F('price'),
            output_field=DecimalField()
        )
    )
    
    price_min = request.GET.get('price_min')
    price_max = request.GET.get('price_max')
    category = request.GET.get('category')
    sort_by = request.GET.get('sort_by')
    brand_slug = request.GET.get('brand')
    
    if brand_slug:
        products = products.filter(brand__slug=brand_slug)
    
    if price_min and price_max:
        products = products.filter(
            effective_price__gte=price_min,
            effective_price__lte=price_max
        )
    
    if category:
        products = products.filter(category__slug=category)
    
    if sort_by == 'price_low_to_high':
        products = products.order_by('effective_price')
    elif sort_by == 'price_high_to_low':
        products = products.order_by('-effective_price')
    elif sort_by == 'newest_first':
        products = products.order_by('-created_at')
    else:
        # Default sorting by popularity/created date
        products = products.order_by('-created_at')
    
    paginator = Paginator(products, 40)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    categories = Category.objects.all()
    brands = Brand.objects.all()
    
    context = {
        'page_obj': page_obj,
        'categories': categories,
        'brands': brands,
        'wishlist_product_ids': wishlist_product_ids,
        'total_products': products.count(),
        'current_filters': {
            'price_min': price_min,
            'price_max': price_max,
            'category': category,
            'sort_by': sort_by,
            'brand': brand_slug
        }
    }
    return render(request, 'shop.html', context)

def home(request):
    # Get wishlist product IDs
    if request.user.is_authenticated:
        try:
            wishlist = Wishlist.objects.get(user=request.user)
            wishlist_items = wishlist.wishlistitem.all()
            wishlist_product_ids = [item.product_id for item in wishlist_items]
        except Wishlist.DoesNotExist:
            wishlist_product_ids = []
    else:
        # For guest users
        session_wishlist = request.session.get('wishlist', [])
        wishlist_product_ids = [int(pid) for pid in session_wishlist if str(pid).isdigit()]
    
    # Get cart product IDs
    cart = get_cart(request)
    cart_items = CartItem.objects.filter(cart=cart)
    cart_product_ids = [item.product_id for item in cart_items]
    
    popular_products = Product.objects.annotate(
        wishlist_count=Count('wishlistitem')
    ).order_by('-wishlist_count')[:10]
    
    most_sold_products = Product.objects.order_by('-sold')[:5]
    latest_reviews = Review.objects.select_related('user', 'product').order_by('-created_at')[:20]
    
    context = {
        'wishlist_product_ids': wishlist_product_ids,
        'cart_product_ids': cart_product_ids,
        'popular_products': popular_products,
        'most_sold': most_sold_products,
        'categories': Category.objects.all()[:6],
        'new_arrivals': Product.objects.order_by('-created_at')[:8],
        'latest_reviews': latest_reviews,
    }
    return render(request, 'home.html', context)

def about_page(request):
    """Display the about/developer profile page"""
    context = {
        'title': 'About Me - Awais Asif',
        'description': 'Full-Stack Web Developer & AI Enthusiast',
        'keywords': 'Django developer, Python, Web Development, AI, Machine Learning, OpenCV, E-commerce',
        'active_page': 'about'
    }
    return render(request, 'about.html', context)

def portfolio_page(request):
    """Display a portfolio page with projects"""
    projects = [
        {
            'id': 1,
            'title': 'BikeSecure AI Parking System',
            'description': 'AI-powered smart bike parking with real-time slot detection',
            'technologies': ['Django', 'OpenCV', 'YOLO', 'PostgreSQL', 'JavaScript'],
            'image_url': 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64',
            'github_url': 'https://github.com/awaisasif/bikesecure',
            'live_url': None
        },
        {
            'id': 2,
            'title': 'NewGate E-commerce Platform',
            'description': 'Complete e-commerce solution with modern features',
            'technologies': ['Django', 'Bootstrap', 'Stripe', 'PostgreSQL', 'JavaScript'],
            'image_url': 'https://images.unsplash.com/photo-1556909114-f6e7ad7d3136',
            'github_url': 'https://github.com/awaisasif/newgate',
            'live_url': None
        },
        {
            'id': 3,
            'title': 'Social Media Analytics Dashboard',
            'description': 'Analytics and SEO optimization platform',
            'technologies': ['Python', 'Django', 'Chart.js', 'Bootstrap', 'PostgreSQL'],
            'image_url': 'https://images.unsplash.com/photo-1611224923853-80b023f02d71',
            'github_url': 'https://github.com/awaisasif/analytics-dashboard',
            'live_url': None
        }
    ]
    
    context = {
        'title': 'My Portfolio',
        'description': 'Check out my latest projects and work',
        'projects': projects,
        'active_page': 'portfolio'
    }
    return render(request, 'portfolio.html', context)

# Optional: If you want the about page accessible only to authenticated users
@login_required
def about_page_private(request):
    """Private about page (requires login)"""
    context = {
        'title': 'About Me',
        'user': request.user,
        'active_page': 'about'
    }
    return render(request, 'about_private.html', context)

@require_POST
def add_to_cart(request, product_id):
    try:
        cart = get_cart(request)
        product = get_object_or_404(Product, id=product_id)
        variant_id = request.POST.get('variant_id')
        
        variant = None
        if variant_id:
            try:
                variant = ProductVariant.objects.get(id=variant_id, product=product)
            except ProductVariant.DoesNotExist:
                pass
        
        # Check if product with same variant already exists in cart
        if variant:
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart, 
                product=product, 
                variant=variant,
                defaults={'quantity': 1}
            )
        else:
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart, 
                product=product,
                defaults={'quantity': 1}
            )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        cart_count = get_cart_count(request)
        
        # Force session save for guests
        if not request.user.is_authenticated:
            request.session.modified = True
            request.session.save()
        
        return JsonResponse({
            'success': True,
            'cart_count': cart_count,
            'variant_saved': variant is not None,
            'message': 'Item added to cart'
        })
    except Exception as e:
        logger.error("Error adding to cart: %s", str(e))
        return JsonResponse({'success': False, 'error': str(e)}, status=500)    

@require_POST
def update_cart(request, product_id, action):
    try:
        cart = get_cart(request)
        product = get_object_or_404(Product, id=product_id)
        variant_id = request.POST.get('variant_id')  # Get variant_id from POST
        
        # Find the cart item with variant (if variant_id provided)
        if variant_id:
            cart_item = CartItem.objects.filter(
                cart=cart, 
                product=product,
                variant_id=variant_id
            ).first()
        else:
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
        cart_count = get_cart_count(request)
        
        # Get updated item
        if variant_id:
            updated_item = CartItem.objects.filter(
                cart=cart, 
                product=product,
                variant_id=variant_id
            ).first()
        else:
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
    
    # DEBUG: Print cart items with variant info
    print("\n=== CART DEBUG ===")
    for item in cart_items:
        print(f"Product: {item.product.name}")
        print(f"  Variant ID: {item.variant_id}")
        print(f"  Variant: {item.variant}")
        print(f"  Has variant: {bool(item.variant)}")
        print("---")
    print("=== END DEBUG ===\n")
    
    total = 0
    for item in cart_items:
        item.subtotal = item.get_subtotal()
        total += item.subtotal

    recommended_products = Product.objects.order_by('-created_at')[:6]

    return render(request, 'cart.html', {
        'cart_items': cart_items,
        'total': total,
        'recommended_products': recommended_products,
    })

@require_http_methods(["DELETE"])
def remove_from_cart(request, item_id):
    cart = get_cart(request)
    
    try:
        if request.user.is_authenticated:
            cart_item = CartItem.objects.get(id=item_id, cart__user=request.user)
        else:
            cart_item = CartItem.objects.get(id=item_id, cart=cart)
        
        cart_item.delete()
        
        cart_items = CartItem.objects.filter(cart=cart)
        total = sum(item.get_subtotal() for item in cart_items)
        
        return JsonResponse({
            'success': True,
            'total': float(total),
            'message': 'Item removed from cart.'
        })
    
    except CartItem.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Cart item not found.'
        }, status=404)

# ========== WISHLIST VIEWS ==========

def wishlist(request):
    if request.user.is_authenticated:
        # Authenticated user - get wishlist from database
        try:
            wishlist_obj = Wishlist.objects.get(user=request.user)
            wishlist_items = wishlist_obj.wishlistitem.select_related('product').all()
        except Wishlist.DoesNotExist:
            wishlist_items = []
        
        # Prepare data for template
        wishlist_data = []
        for item in wishlist_items:
            discount_amount = 0
            if item.product.discount_price:
                discount_amount = float(item.product.price) - float(item.product.discount_price)
            
            wishlist_data.append({
                'id': item.id,
                'product': item.product,
                'discount_amount': discount_amount,
                'notes': item.notes,
                'priority': item.priority,
                'added_at': item.added_at
            })
        
        is_guest = False
        wishlist_product_ids = [item['product'].id for item in wishlist_data]
    else:
        # Guest user - get wishlist from session
        session_wishlist = request.session.get('wishlist', [])
        
        # Convert session data to product objects
        wishlist_data = []
        for product_id in session_wishlist:
            try:
                product = Product.objects.get(id=product_id, available=True)
                
                discount_amount = 0
                if product.discount_price:
                    discount_amount = float(product.price) - float(product.discount_price)
                
                wishlist_data.append({
                    'id': f"guest_{product_id}",
                    'product': product,
                    'discount_amount': discount_amount,
                    'notes': None,
                    'priority': None,
                    'added_at': None
                })
            except Product.DoesNotExist:
                # Remove invalid product IDs from session
                if product_id in session_wishlist:
                    session_wishlist.remove(product_id)
        
        # Update session with valid IDs
        request.session['wishlist'] = session_wishlist
        request.session.modified = True
        is_guest = True
        wishlist_product_ids = session_wishlist
    
    # Get recommended products (excluding wishlisted products)
    if wishlist_data:
        # Get wishlisted product IDs
        wishlisted_ids = [item['product'].id for item in wishlist_data]
        
        # Get recommendations based on wishlisted categories
        wishlist_categories = set(item['product'].category for item in wishlist_data if item['product'].category)
        
        if wishlist_categories:
            recommended = Product.objects.filter(
                category__in=wishlist_categories,
                available=True
            ).exclude(
                id__in=wishlisted_ids
            ).order_by('-created_at')[:8]
        else:
            # If no categories, get popular products
            recommended = Product.objects.filter(
                available=True
            ).exclude(
                id__in=wishlisted_ids
            ).order_by('-created_at')[:8]
    else:
        # If wishlist is empty, get popular products
        recommended = Product.objects.filter(
            available=True
        ).order_by('-created_at')[:8]
    
    # Prepare recommended products data
    recommended_data = []
    for product in recommended:
        discount_amount = 0
        if product.discount_price:
            discount_amount = float(product.price) - float(product.discount_price)
        
        recommended_data.append({
            'product': product,
            'discount_amount': discount_amount
        })
    
    context = {
        'wishlist_items': wishlist_data,
        'is_guest': is_guest,
        'recommended_products': recommended_data,
        'wishlist_product_ids': wishlist_product_ids,
    }
    
    return render(request, 'wishlist.html', context)

# shop/views.py - Update add_to_wishlist function

@require_POST
@csrf_exempt  # Add this for testing
def add_to_wishlist(request, product_id):
    """Add or remove product from wishlist"""
    try:
        print(f"Adding to wishlist - Product ID: {product_id}, User: {request.user}")
        
        if request.user.is_authenticated:
            # Authenticated user
            wishlist, created = Wishlist.objects.get_or_create(user=request.user)
            item, item_created = WishlistItem.objects.get_or_create(
                wishlist=wishlist, 
                product_id=product_id
            )
            
            if not item_created:
                # Item already exists, remove it
                item.delete()
                action = 'removed'
                wishlist_count = WishlistItem.objects.filter(wishlist=wishlist).count()
            else:
                action = 'added'
                wishlist_count = WishlistItem.objects.filter(wishlist=wishlist).count()
        else:
            # Guest user - use session
            session_wishlist = request.session.get('wishlist', [])
            
            # Convert product_id to string for session storage
            product_id_str = str(product_id)
            
            if product_id_str in session_wishlist:
                # Remove from wishlist
                session_wishlist.remove(product_id_str)
                action = 'removed'
            else:
                # Add to wishlist
                session_wishlist.append(product_id_str)
                action = 'added'
            
            # Update session
            request.session['wishlist'] = session_wishlist
            request.session.modified = True
            wishlist_count = len(session_wishlist)
        
        print(f"Wishlist action: {action}, Count: {wishlist_count}")
        
        return JsonResponse({
            'success': True, 
            'wishlist_count': wishlist_count, 
            'action': action,
            'message': f'Item {action} wishlist'
        })
    except Exception as e:
        print(f"Error in add_to_wishlist: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["POST", "DELETE"])
def delete_wishlist_item(request, item_id):
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
            product_id = str(item_id)
            if product_id in wishlist:
                wishlist.remove(product_id)
                request.session['wishlist'] = wishlist
                request.session.modified = True
            return JsonResponse({'success': True})
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid item id.'}, status=400)

# Add a separate view for guest wishlist removal if needed
@require_http_methods(["POST"])
def remove_guest_wishlist_item(request, product_id):
    if not request.user.is_authenticated:
        wishlist = request.session.get('wishlist', [])
        product_id_str = str(product_id)
        if product_id_str in wishlist:
            wishlist.remove(product_id_str)
            request.session['wishlist'] = wishlist
            request.session.modified = True
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Item not found.'}, status=404)
    return JsonResponse({'success': False, 'error': 'User is authenticated.'}, status=400)

# ========== DASHBOARD VIEWS ==========
def admin_dashboard(request):
    days = int(request.GET.get('days', 30))
    date_range = timezone.now() - timedelta(days=days)
    prev_date_range = timezone.now() - timedelta(days=days*2)
    
    # Get orders with prefetched items for proper total calculation
    orders = Order.objects.filter(created_at__gte=date_range).prefetch_related(
        Prefetch('items', queryset=OrderItem.objects.select_related('product', 'variant'))
    )
    orders_count = orders.count()
    
    # Calculate total sales using the Order.final_total property
    total_sales = sum(order.final_total for order in orders)
    
    prev_orders = Order.objects.filter(
        created_at__gte=prev_date_range, 
        created_at__lt=date_range
    ).prefetch_related('items')
    prev_sales = sum(order.final_total for order in prev_orders)
    
    prev_orders_count = prev_orders.count()
    orders_change = ((orders_count - prev_orders_count) / prev_orders_count * 100) if prev_orders_count else 0
    sales_change = ((total_sales - prev_sales) / prev_sales * 100) if prev_sales else 0
    
    revenue = total_sales * Decimal('0.85')
    prev_revenue = prev_sales * Decimal('0.85')
    revenue_change = ((revenue - prev_revenue) / prev_revenue * 100) if prev_revenue else 0
    
    new_customers = User.objects.filter(date_joined__gte=date_range).count()
    prev_customers = User.objects.filter(
        date_joined__gte=prev_date_range, 
        date_joined__lt=date_range
    ).count()
    customers_change = ((new_customers - prev_customers) / prev_customers * 100) if prev_customers else 0
    
    top_products = Product.objects.annotate(
        order_count=Count('order_items', filter=Q(order_items__order__created_at__gte=date_range))
    ).order_by('-order_count')[:5]
    
    recent_orders = orders.order_by('-created_at')[:5]
    new_customers_list = User.objects.filter(date_joined__gte=date_range).order_by('-date_joined')[:5]
    
    weekly_labels = []
    weekly_data = []
    for i in range(7, 0, -1):
        day = timezone.now() - timedelta(days=i)
        weekly_labels.append(day.strftime('%a'))
        day_orders = Order.objects.filter(created_at__date=day.date()).prefetch_related('items')
        day_sales = sum(order.final_total for order in day_orders)
        weekly_data.append(float(day_sales))
    
    monthly_labels = []
    monthly_data = []
    for i in range(12, 0, -1):
        month = timezone.now() - timedelta(days=30*i)
        monthly_labels.append(month.strftime('%b'))
        month_orders = Order.objects.filter(
            created_at__month=month.month,
            created_at__year=month.year
        ).prefetch_related('items')
        month_sales = sum(order.final_total for order in month_orders)
        monthly_data.append(float(month_sales))
    
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
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('search', '')
    
    orders = Order.objects.select_related(
        'user',
        'delivery_address'
    ).prefetch_related(
        Prefetch('items', queryset=OrderItem.objects.select_related(
            'product', 
            'variant'
        ).prefetch_related('product__images'))
    ).order_by('-created_at')
    
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
    
    # Add pagination
    paginator = Paginator(orders, 10)  # 10 orders per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'dashboard/orders.html', {
        'orders': page_obj,
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
        order = get_object_or_404(Order, id=order_id)
        order.status = 'cancelled'
        order.save()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'message': 'Invalid request'})

def product_list(request):
    products = Product.objects.select_related("category", "brand").prefetch_related("images", "variants")
    
    paginator = Paginator(products, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    context = {
        "products": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "page_obj": page_obj,
    }
    return render(request, "dashboard/product_list.html", context)