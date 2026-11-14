from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class User(AbstractUser):
    """Single account model for both workers and employers."""

    class Role(models.TextChoices):
        WORKER = 'worker', 'Worker'
        EMPLOYER = 'employer', 'Employer'
        ADMIN = 'admin', 'Admin'

    class Language(models.TextChoices):
        ENGLISH = 'en', 'English'
        HINDI = 'hi', 'Hindi'
        MARATHI = 'mr', 'Marathi'

    name = models.CharField(max_length=120, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.WORKER)
    phone = models.CharField(max_length=15, unique=True, null=True, blank=True)
    whatsapp_number = models.CharField(max_length=20, blank=True)
    preferred_language = models.CharField(
        max_length=8, choices=Language.choices, default=Language.ENGLISH
    )

    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'
        constraints = [
            models.UniqueConstraint(
                Lower('email'),
                condition=~Q(email=''),
                name='accounts_user_email_ci_unique',
            ),
        ]

    @property
    def display_name(self):
        return self.name or self.get_full_name() or self.email or self.get_username()

    @property
    def is_worker(self):
        return self.role == self.Role.WORKER

    @property
    def is_employer(self):
        return self.role == self.Role.EMPLOYER
