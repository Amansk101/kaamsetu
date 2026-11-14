from django.conf import settings
from django.db import models


class Area(models.Model):
    """Village / town / pincode level location used for distance-based matching."""

    name = models.CharField(max_length=120)
    district = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    pincode = models.CharField(max_length=10, blank=True, db_index=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['state', 'district', 'name']
        verbose_name_plural = 'Areas'

    def __str__(self):
        parts = [self.name, self.district]
        return ', '.join(p for p in parts if p)


class Skill(models.Model):
    """Master list of trades that workers can be verified in."""

    name = models.CharField(max_length=80, unique=True)
    category = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Notification(models.Model):
    """Per-user activity feed (applications, jobs, profile updates)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications'
    )
    title = models.CharField(max_length=180)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=240, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', '-created_at'])]

    def __str__(self):
        return f'{self.title} → {self.user}'
