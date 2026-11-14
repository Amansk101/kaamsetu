from django.contrib import admin

from .models import AgentLog


@admin.register(AgentLog)
class AgentLogAdmin(admin.ModelAdmin):
    list_display = ('agent', 'subject_type', 'subject_id', 'created_at')
    list_filter = ('agent', 'subject_type')
    readonly_fields = ('agent', 'subject_type', 'subject_id', 'input_summary', 'output', 'created_at')
