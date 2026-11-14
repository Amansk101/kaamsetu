from django.contrib import admin

from .models import Area, Skill


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'district', 'state', 'pincode')
    search_fields = ('name', 'district', 'pincode')
    list_filter = ('state',)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_active')
    list_filter = ('is_active', 'category')
    search_fields = ('name',)
