from django.db import models


class AgentLog(models.Model):
    """Har AI agent decision ka transparent record (bias audit + debugging)."""

    agent = models.CharField(max_length=64)
    subject_type = models.CharField(max_length=64, blank=True)
    subject_id = models.CharField(max_length=64, blank=True)
    input_summary = models.TextField(blank=True)
    output = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.agent} @ {self.created_at:%Y-%m-%d %H:%M}'
