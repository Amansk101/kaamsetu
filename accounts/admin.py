from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class KaamSetuUserAdmin(UserAdmin):
    list_display = ('username', 'role', 'phone', 'preferred_language', 'is_staff')
    list_filter = ('role', 'preferred_language', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('KaamSetu', {'fields': ('role', 'phone', 'whatsapp_number', 'preferred_language')}),
    )
