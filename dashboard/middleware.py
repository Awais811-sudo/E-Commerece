from django.http import HttpResponseForbidden
from .models import AdminAccess
from django.shortcuts import redirect
class AdminPanelAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/admin-panel/'):
            if not request.user.is_authenticated:
                return redirect('admin_login')
                
            try:
                access = AdminAccess.objects.get(user=request.user)
                if not (access.is_admin or access.is_staff):
                    return HttpResponseForbidden("Access Denied")
            except AdminAccess.DoesNotExist:
                return HttpResponseForbidden("Access Denied")

        return self.get_response(request)