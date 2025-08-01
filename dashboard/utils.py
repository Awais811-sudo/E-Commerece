from .models import AdminAccess

def has_admin_permission(user, permission):
    try:
        access = AdminAccess.objects.get(user=user)
        if access.is_admin:
            return True
        return permission in access.permissions.get('allowed', [])
    except AdminAccess.DoesNotExist:
        return False