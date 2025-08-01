from django.db import models
from shop.models import User

class AdminAccess(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    is_admin = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    permissions = models.JSONField(default=dict)

class PixelTracking(models.Model):
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    page_url = models.URLField()
    action = models.CharField(max_length=100)
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField()


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=100)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField()