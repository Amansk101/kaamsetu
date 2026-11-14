from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from employers.models import EmployerProfile
from .models import Job, JobVerification


class JobPostingFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.employer_user = User.objects.create_user(
            username='jobs@example.com', email='jobs@example.com',
            password='Test@1234', role=User.Role.EMPLOYER,
        )
        self.employer = EmployerProfile.objects.create(
            user=self.employer_user, business_name='Local Services',
        )

    def test_job_post_form_loads_its_local_component_styles(self):
        response = self.client.get(reverse('jobs:post_job'))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.employer_user)
        response = self.client.get(reverse('jobs:post_job'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'css/kaamsetu.css')
        self.assertContains(response, 'class="glass"')
        self.assertContains(response, 'name="raw_description"')

    def test_safe_listing_is_published_with_a_verification_record(self):
        self.client.force_login(self.employer_user)
        response = self.client.post(reverse('jobs:post_job'), {
            'raw_description': 'Need 2 electricians, 15000-20000 per month in Pune',
        })
        job = Job.objects.get(employer=self.employer)
        self.assertRedirects(response, reverse('jobs:detail', args=[job.pk]))
        self.assertEqual(job.status, Job.Status.ACTIVE)
        self.assertEqual(job.workers_needed, 2)
        self.assertEqual(job.wage_period, Job.WagePeriod.MONTH)
        self.assertEqual(job.verification.status, JobVerification.Status.PASSED)

    def test_upfront_fee_listing_is_blocked(self):
        self.client.force_login(self.employer_user)
        response = self.client.post(reverse('jobs:post_job'), {
            'raw_description': 'Need electrician in Pune. Pay registration fee 500 to apply.',
        })
        job = Job.objects.get(employer=self.employer)
        self.assertRedirects(response, reverse('jobs:detail', args=[job.pk]))
        self.assertEqual(job.status, Job.Status.REJECTED)
        self.assertEqual(job.verification.status, JobVerification.Status.BLOCKED)
