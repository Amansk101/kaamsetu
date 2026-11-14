from django.contrib import admin

from .models import EmployerProfile


@admin.register(EmployerProfile)
class EmployerProfileAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'business_type', 'area', 'verified')
    list_filter = ('verified',)
    search_fields = ('business_name', 'user__username')
