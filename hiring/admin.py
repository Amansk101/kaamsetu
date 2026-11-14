from django.contrib import admin

from .models import (
    Connection,
    ConsentGrant,
    FollowUp,
    FollowUpResponse,
    JobInterest,
)


class FollowUpResponseInline(admin.StackedInline):
    model = FollowUpResponse
    extra = 0


@admin.register(JobInterest)
class JobInterestAdmin(admin.ModelAdmin):
    list_display = ('worker', 'job', 'status', 'match_score', 'created_at')
    list_filter = ('status',)


@admin.register(ConsentGrant)
class ConsentGrantAdmin(admin.ModelAdmin):
    list_display = ('interest', 'share_name', 'share_phone', 'share_city', 'is_active')
    list_filter = ('is_active',)


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = ('worker', 'job', 'status', 'hired_at')
    list_filter = ('status',)


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ('connection', 'stage', 'due_date', 'status')
    list_filter = ('stage', 'status')
    inlines = [FollowUpResponseInline]
