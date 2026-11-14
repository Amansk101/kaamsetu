from django.db import models

from jobs.models import Job
from workers.models import WorkerProfile


class JobInterest(models.Model):
    """Worker ne job par 'Interested' click kiya."""

    class Status(models.TextChoices):
        INTERESTED = 'interested', 'Interested'
        CONSENT_REQUESTED = 'consent_requested', 'Consent requested'
        WITHDRAWN = 'withdrawn', 'Withdrawn'
        DECLINED = 'declined', 'Declined'
        CONNECTED = 'connected', 'Connected'
        HIRED = 'hired', 'Hired'
        CLOSED = 'closed', 'Closed'

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='interests')
    worker = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE, related_name='interests'
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.INTERESTED)
    match_score = models.PositiveSmallIntegerField(default=0)
    match_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    consent_requested = models.BooleanField(default=False)

    class Meta:
        unique_together = ('job', 'worker')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.worker} → {self.job} ({self.get_status_display()})'


class ConsentGrant(models.Model):
    """HARD GATE: employer ko kya dikhega, worker decide karta hai."""

    interest = models.OneToOneField(
        JobInterest, on_delete=models.CASCADE, related_name='consent'
    )
    share_name = models.BooleanField(default=True)
    share_phone = models.BooleanField(default=False)
    share_email = models.BooleanField(default=False)
    share_city = models.BooleanField(default=True)
    share_skills = models.BooleanField(default=True)
    share_video = models.BooleanField(default=False)
    share_education = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    granted_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    def shared_fields(self):
        fields = {
            'share_name': 'Name',
            'share_phone': 'Phone',
            'share_email': 'Email',
            'share_city': 'City / Area',
            'share_skills': 'Skills & level',
            'share_video': 'Skill video',
            'share_education': 'Education',
        }
        return [label for field, label in fields.items() if getattr(self, field)]

    def __str__(self):
        return f'Consent #{self.pk} for {self.interest}'


class Connection(models.Model):
    """Worker consent dene ke baad bani connection."""

    class Status(models.TextChoices):
        CONNECTED = 'connected', 'Connected'
        CONTACTED = 'contacted', 'Contacted'
        HIRED = 'hired', 'Hired'
        REJECTED_EMPLOYER = 'rejected_employer', 'Not selected by employer'
        REJECTED_WORKER = 'rejected_worker', 'Declined by worker'
        CLOSED = 'closed', 'Closed'

    interest = models.OneToOneField(
        JobInterest, on_delete=models.CASCADE, related_name='connection'
    )
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='connections')
    worker = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE, related_name='connections'
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONNECTED)
    employer_notes = models.TextField(blank=True)
    hired_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.worker} ↔ {self.job}'


class FollowUp(models.Model):
    """Retention agent: day 7 / 30 / 90 check-ins."""

    class Stage(models.TextChoices):
        DAY7 = 'day7', 'Day 7'
        DAY30 = 'day30', 'Day 30'
        DAY90 = 'day90', 'Day 90'

    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        SENT = 'sent', 'Sent'
        RESPONDED = 'responded', 'Responded'
        NO_RESPONSE = 'no_response', 'No response'
        ESCALATED = 'escalated', 'Escalated'

    connection = models.ForeignKey(
        Connection, on_delete=models.CASCADE, related_name='followups'
    )
    stage = models.CharField(max_length=8, choices=Stage.choices)
    due_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED)
    channel = models.CharField(max_length=16, default='whatsapp')
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('connection', 'stage')
        ordering = ['due_date']

    def __str__(self):
        return f'{self.connection} - {self.get_stage_display()}'


class FollowUpResponse(models.Model):
    follow_up = models.OneToOneField(
        FollowUp, on_delete=models.CASCADE, related_name='response'
    )
    payment_on_time = models.BooleanField(null=True, blank=True)
    payment_issue = models.BooleanField(default=False)
    satisfaction = models.PositiveSmallIntegerField(null=True, blank=True, help_text='1-5')
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Response for {self.follow_up}'
