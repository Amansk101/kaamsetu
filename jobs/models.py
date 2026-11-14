from django.db import models

from core.models import Area, Skill
from employers.models import EmployerProfile
from workers.models import WorkerProfile


class Job(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PENDING = 'pending', 'Pending verification'
        ACTIVE = 'active', 'Active'
        REJECTED = 'rejected', 'Rejected'
        CLOSED = 'closed', 'Closed'

    class WagePeriod(models.TextChoices):
        HOUR = 'hour', 'Per hour'
        DAY = 'day', 'Per day'
        MONTH = 'month', 'Per month'

    class JobType(models.TextChoices):
        FULL_TIME = 'full_time', 'Full time'
        PART_TIME = 'part_time', 'Part time'
        SEASONAL = 'seasonal', 'Seasonal'
        CONTRACT = 'contract', 'Contract'

    employer = models.ForeignKey(
        EmployerProfile, on_delete=models.CASCADE, related_name='jobs'
    )
    title = models.CharField(max_length=160)
    company_name = models.CharField(max_length=160, blank=True)
    location = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    required_skills = models.JSONField(default=list, blank=True)
    raw_description = models.TextField(
        blank=True, help_text='Original free-text / voice transcript from the employer'
    )
    skill = models.ForeignKey(
        Skill, on_delete=models.SET_NULL, null=True, blank=True, related_name='jobs'
    )
    workers_needed = models.PositiveSmallIntegerField(default=1)
    wage_min = models.PositiveIntegerField(null=True, blank=True)
    wage_max = models.PositiveIntegerField(null=True, blank=True)
    wage_period = models.CharField(
        max_length=8, choices=WagePeriod.choices, default=WagePeriod.DAY
    )
    job_type = models.CharField(
        max_length=16, choices=JobType.choices, default=JobType.FULL_TIME
    )
    area = models.ForeignKey(
        Area, on_delete=models.SET_NULL, null=True, blank=True, related_name='jobs'
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_via = models.CharField(max_length=16, default='web')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', '-created_at'])]

    def __str__(self):
        return self.title

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    @property
    def company_label(self):
        return self.company_name or self.employer.business_name

    @property
    def location_label(self):
        return self.location or (str(self.area) if self.area else '')

    @property
    def skills_list(self):
        if self.required_skills:
            return [str(s) for s in self.required_skills]
        if self.skill:
            return [self.skill.name]
        return []

    @property
    def salary_label(self):
        if self.wage_min is None and self.wage_max is None:
            return ''
        if self.wage_min is not None and self.wage_max is not None and self.wage_min != self.wage_max:
            amount = f'₹{self.wage_min:,} – ₹{self.wage_max:,}'
        else:
            amount = f'₹{(self.wage_min or self.wage_max):,}'
        return f'{amount} / {self.get_wage_period_display().lower().replace("per ", "")}'


class JobVerification(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PASSED = 'passed', 'Passed'
        FLAGGED = 'flagged', 'Flagged for review'
        BLOCKED = 'blocked', 'Blocked'

    job = models.OneToOneField(
        Job, on_delete=models.CASCADE, related_name='verification'
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    risk_score = models.PositiveSmallIntegerField(
        default=0, help_text='0 = safe, 100 = high fraud risk'
    )
    flags = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True)
    structured_data = models.JSONField(default=dict, blank=True)
    checked_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Verification for {self.job} - {self.get_status_display()}'


class SavedJob(models.Model):
    """Worker ka bookmarked job."""

    worker = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE, related_name='saved_jobs'
    )
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='saved_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('worker', 'job')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.worker} saved {self.job}'


class JobApplication(models.Model):
    """Worker ne job ke liye apply kiya (ek worker, ek job — ek hi baar)."""

    class Status(models.TextChoices):
        APPLIED = 'Applied', 'Applied'
        UNDER_REVIEW = 'Under Review', 'Under Review'
        SHORTLISTED = 'Shortlisted', 'Shortlisted'
        INTERVIEW = 'Interview', 'Interview'
        SELECTED = 'Selected', 'Selected'
        REJECTED = 'Rejected', 'Rejected'
        HIRED = 'Hired', 'Hired'

    worker = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE, related_name='applications'
    )
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='applications')
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.APPLIED
    )
    match_score = models.PositiveSmallIntegerField(default=0)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('worker', 'job')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['job', 'status']),
            models.Index(fields=['worker', 'status']),
        ]

    def __str__(self):
        return f'{self.worker} → {self.job} ({self.status})'
