from django.contrib import admin

from .models import Education, SkillAssessment, WorkerProfile, WorkerSkill


class EducationInline(admin.TabularInline):
    model = Education
    extra = 0


class WorkerSkillInline(admin.TabularInline):
    model = WorkerSkill
    extra = 0


@admin.register(WorkerProfile)
class WorkerProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'area', 'availability', 'verified', 'profile_completed')
    list_filter = ('verified', 'profile_completed', 'availability')
    search_fields = ('full_name', 'user__username', 'user__phone')
    inlines = [WorkerSkillInline, EducationInline]


@admin.register(SkillAssessment)
class SkillAssessmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'worker', 'skill', 'ai_level', 'ai_confidence', 'status')
    list_filter = ('status', 'ai_level')
