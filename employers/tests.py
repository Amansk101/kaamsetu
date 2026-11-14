from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import EmployerProfile
from hiring.models import ConsentGrant, JobInterest
from jobs.models import Job, JobApplication
from workers.models import WorkerProfile


class EmployerDashboardTests(TestCase):
    def test_dashboard_renders_empty_pipeline_and_employer_actions(self):
        user = get_user_model().objects.create_user(
            username='employer@example.com', email='employer@example.com',
            password='Test@1234', role='employer',
        )
        EmployerProfile.objects.create(user=user, business_name='Local Services')
        self.client.force_login(user)

        response = self.client.get('/employer/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Application pipeline')
        self.assertContains(response, 'No applications yet')
        self.assertContains(response, 'Find Workers')
        self.assertNotContains(response, 'data-background-video')
        self.assertContains(response, 'hiring-conversation.webp')

    def test_my_jobs_uses_real_records_and_per_job_application_counts(self):
        User = get_user_model()
        employer_user = User.objects.create_user(
            username='jobs-employer@example.com', email='jobs-employer@example.com',
            password='Test@1234', role='employer',
        )
        employer = EmployerProfile.objects.create(user=employer_user, business_name='Local Works')
        job = Job.objects.create(
            employer=employer, title='Industrial Electrician',
            description='Install and maintain safe electrical systems at local sites.',
            required_skills=['Electrical repair', 'Safety testing'],
            status=Job.Status.ACTIVE, location='Pune', workers_needed=3,
            wage_min=18000, wage_max=24000, wage_period=Job.WagePeriod.MONTH,
        )
        worker_one_user = User.objects.create_user(
            username='applicant-one@example.com', email='applicant-one@example.com',
            password='Test@1234', role='worker',
        )
        worker_two_user = User.objects.create_user(
            username='applicant-two@example.com', email='applicant-two@example.com',
            password='Test@1234', role='worker',
        )
        worker_one = WorkerProfile.objects.create(user=worker_one_user, full_name='Aman Shaikh')
        worker_two = WorkerProfile.objects.create(user=worker_two_user, full_name='Ravi Kumar')
        JobApplication.objects.create(job=job, worker=worker_one, status=JobApplication.Status.APPLIED)
        JobApplication.objects.create(job=job, worker=worker_two, status=JobApplication.Status.SHORTLISTED)

        self.client.force_login(employer_user)
        response = self.client.get(reverse('employers:jobs'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Industrial Electrician')
        self.assertContains(response, 'Electrical repair')
        self.assertContains(response, '2')
        self.assertContains(response, 'View Details')
        self.assertContains(response, 'Manage Candidates')

        details = self.client.get(reverse('employers:job_detail', args=[job.pk]))
        self.assertEqual(details.status_code, 200)
        self.assertContains(details, job.description)
        self.assertEqual(details.context['job'].applicant_count, 2)
        self.assertEqual(details.context['job'].pending_count, 1)
        self.assertEqual(details.context['job'].shortlisted_count, 1)

        applications = self.client.get(reverse('employers:applications'), {'job': job.pk})
        self.assertEqual(applications.status_code, 200)
        self.assertEqual(applications.context['total'], 2)

        edit_page = self.client.get(reverse('employers:edit_job', args=[job.pk]))
        self.assertEqual(edit_page.status_code, 200)
        updated = self.client.post(reverse('employers:edit_job', args=[job.pk]), {
            'title': 'Maintenance Electrician', 'company_name': 'Local Works',
            'location': 'Pune', 'job_type': Job.JobType.FULL_TIME,
            'wage_min': '19000', 'wage_max': '25000',
            'skills': 'Electrical repair, Safety testing',
            'description': 'Maintain equipment and test electrical systems safely.',
        })
        self.assertEqual(updated.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.title, 'Maintenance Electrician')
        candidates = self.client.get(reverse('hiring:job_candidates', args=[job.pk]))
        self.assertEqual(candidates.status_code, 200)

        no_match = self.client.get(reverse('employers:jobs'), {'q': 'welder'})
        self.assertEqual(no_match.context['total'], 0)
        closed = self.client.post(reverse('employers:close_job', args=[job.pk]))
        self.assertEqual(closed.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.CLOSED)

    def test_employer_contact_links_work_without_profile_detail_consent(self):
        User = get_user_model()
        employer_user = User.objects.create_user(
            username='privacy-employer@example.com', email='privacy-employer@example.com',
            password='Test@1234', role='employer',
        )
        employer = EmployerProfile.objects.create(user=employer_user, business_name='Local Services')
        worker_user = User.objects.create_user(
            username='worker-private@example.com', email='worker-private@example.com',
            password='Test@1234', role='worker', phone='9876543210',
        )
        worker = WorkerProfile.objects.create(
            user=worker_user, full_name='Aman Shaikh', mobile='9876543210',
            email='worker-private@example.com',
        )
        self.client.force_login(employer_user)
        url = reverse('employers:worker_detail', args=[worker.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="tel:9876543210"')
        self.assertContains(response, 'href="mailto:worker-private%40example.com"')
        self.assertContains(response, 'mail.google.com/mail/?view=cm&amp;fs=1&amp;to=worker-private%40example.com')
        self.assertContains(response, 'Open email app')
        self.assertNotContains(response, 'Request permission to review additional profile details')

        job = Job.objects.create(
            employer=employer, title='Electrician', status=Job.Status.ACTIVE,
        )
        interest = JobInterest.objects.create(job=job, worker=worker)
        ConsentGrant.objects.create(interest=interest, share_phone=True, share_email=False)
        response = self.client.get(url)
        self.assertContains(response, 'href="tel:9876543210"')
        self.assertContains(response, 'href="mailto:worker-private%40example.com"')

    def test_legacy_consent_request_endpoint_no_longer_creates_a_dashboard_request(self):
        User = get_user_model()
        employer_user = User.objects.create_user(
            username='request-employer@example.com', email='request-employer@example.com',
            password='Test@1234', role='employer',
        )
        employer = EmployerProfile.objects.create(user=employer_user, business_name='Local Services')
        worker_user = User.objects.create_user(
            username='request-worker@example.com', email='request-worker@example.com',
            password='Test@1234', role='worker',
        )
        worker = WorkerProfile.objects.create(user=worker_user, full_name='Ravi Kumar')
        job = Job.objects.create(employer=employer, title='Plumber', status=Job.Status.ACTIVE)

        self.client.force_login(employer_user)
        response = self.client.post(
            reverse('hiring:request_consent', args=[worker.pk]), {'job_id': job.pk},
        )
        self.assertRedirects(response, reverse('employers:worker_detail', args=[worker.pk]))
        self.assertFalse(JobInterest.objects.filter(job=job, worker=worker).exists())
