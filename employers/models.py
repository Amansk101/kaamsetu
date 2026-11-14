from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from core.models import Area


class EmployerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='employer_profile'
    )
    business_name = models.CharField(max_length=160)
    business_type = models.CharField(max_length=120, blank=True)
    contact_name = models.CharField(max_length=120, blank=True)
    contact_date_of_birth = models.DateField(null=True, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    pincode = models.CharField(max_length=6, blank=True)
    area = models.ForeignKey(
        Area, on_delete=models.SET_NULL, null=True, blank=True, related_name='employers'
    )
    address = models.CharField(max_length=240, blank=True)
    description = models.TextField(blank=True)
    verified = models.BooleanField(default=False)
    onboarding_completed = models.BooleanField(default=False)
    job_alerts = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def contact_age(self):
        if not self.contact_date_of_birth:
            return None
        today = timezone.localdate()
        birth = self.contact_date_of_birth
        return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))

    @property
    def profile_completion(self):
        values = (
            self.business_name, self.business_type, self.contact_name, self.city,
            self.state, self.pincode, self.address, self.description,
        )
        return round(sum(bool(str(value or '').strip()) for value in values) * 100 / len(values))

    def __str__(self):
        return self.business_name


class Feedback(models.Model):
    """Employer ka post-hiring follow-up (Day 7 / 30 / 90 check-in)."""

    class Milestone(models.IntegerChoices):
        DAY7 = 7, 'Day 7'
        DAY30 = 30, 'Day 30'
        DAY90 = 90, 'Day 90'

    application = models.ForeignKey(
        'jobs.JobApplication', on_delete=models.CASCADE, related_name='feedback'
    )
    milestone = models.PositiveSmallIntegerField(choices=Milestone.choices)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('application', 'milestone')
        ordering = ['milestone']

    def __str__(self):
        return f'{self.application} · Day {self.milestone}'
