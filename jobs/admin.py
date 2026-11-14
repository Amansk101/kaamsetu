from django.contrib import admin

from .models import Job, JobVerification


class JobVerificationInline(admin.StackedInline):
    model = JobVerification
    extra = 0


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('title', 'employer', 'skill', 'area', 'wage_min', 'wage_max', 'status')
    list_filter = ('status', 'job_type', 'wage_period')
    search_fields = ('title', 'employer__business_name')
    inlines = [JobVerificationInline]


@admin.register(JobVerification)
class JobVerificationAdmin(admin.ModelAdmin):
    list_display = ('job', 'status', 'risk_score', 'checked_at')
    list_filter = ('status',)
