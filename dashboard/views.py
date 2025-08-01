# from django.contrib.auth.decorators import login_required
# from django.utils.decorators import method_decorator
# from django.views import View
# from shop.models import AdminAccess
# from django.http import HttpResponseForbidden
# from django.shortcuts import render
# from django.views import View
# from django.http import JsonResponse
# from .utils import has_admin_permission
# from shop.forms import ProductForm
# from django.views import View
# from django.http import JsonResponse
# from django.utils.decorators import method_decorator
# from django.views.decorators.csrf import csrf_exempt
# from shop.forms import ProductForm
# from .utils import has_admin_permission
# from channels.layers import get_channel_layer
# from asgiref.sync import async_to_sync

# def trigger_update():
#     channel_layer = get_channel_layer()
#     async_to_sync(channel_layer.group_send)(
#         "dashboard",
#         {
#             "type": "send.update",
#             "data": get_live_sales_data()
#         }
#     )

# def get_live_sales_data():
#     return {
#         'amount': Order.objects.filter(
#             created_at__gte=timezone.now() - timedelta(minutes=5)
#             .aggregate(total=Sum('total'))['total'] or 0,
#         'orders': Order.objects.filter(
#             created_at__gte=timezone.now() - timedelta(minutes=5)).count(),
#         'timestamp': timezone.now().isoformat()
#     }



# @method_decorator(csrf_exempt, name='dispatch')
# class ProductManagementView(View):
    
#     def post(self, request):
#         # Authentication check
#         if not request.user.is_authenticated:
#             return JsonResponse({
#                 'status': 'error',
#                 'message': 'Authentication required'
#             }, status=401)

#         # Permission check
#         if not has_admin_permission(request.user, 'manage_products'):
#             return JsonResponse({
#                 'status': 'error',
#                 'message': 'Insufficient permissions'
#             }, status=403)

#         # Form handling
#         form = ProductForm(request.POST, request.FILES)
#         if form.is_valid():
#             try:
#                 product = form.save()
#                 return JsonResponse({
#                     'status': 'success',
#                     'product_id': product.id,
#                     'product_name': product.name,
#                     'message': 'Product created successfully'
#                 })
#             except Exception as e:
#                 return JsonResponse({
#                     'status': 'error',
#                     'message': f'Save error: {str(e)}'
#                 }, status=500)

#         # Return form errors
#         return JsonResponse({
#             'status': 'error',
#             'errors': form.errors.get_json_data()
#         }, status=400)
# class ProductManagementView(View):
#     def post(self, request):
#         if not has_admin_permission(request.user, 'manage_products'):
#             return JsonResponse({'status': 'error', 'message': 'Forbidden'}, status=403)
            
#         form = ProductForm(request.POST, request.FILES)
#         if form.is_valid():
#             product = form.save()
#             return JsonResponse({'status': 'success', 'product_id': product.id})
            
#         return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)



# class AdminDashboardView(View):
#     @method_decorator(login_required)
#     def get(self, request):
#         try:
#             access = AdminAccess.objects.get(user=request.user)
#             if not access.is_admin:
#                 return HttpResponseForbidden()
                
#             # Get analytics data
#             context = {
#                 'sales_data': get_sales_analytics(),
#                 'top_products': get_top_products(),
#                 'user_growth': get_user_growth(),
#                 'page_views': get_page_views()
#             }
#             return render(request, 'admin/dashboard.html', context)
            
#         except AdminAccess.DoesNotExist:
#             return HttpResponseForbidden()

# def get_sales_analytics():
#     # Implement time-based sales aggregation
#     pass

# def get_top_products():
#     # Get most ordered products
#     pass