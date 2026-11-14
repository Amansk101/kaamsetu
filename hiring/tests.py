from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from employers.models import EmployerProfile
from jobs.models import Job, JobApplication
from workers.models import WorkerProfile

from .models import Connection, ConsentGrant, FollowUp, FollowUpResponse, JobInterest


class HiringJourneyTests(TestCase):
    def setUp(self):
        User = get_user_model()
        employer_user = User.objects.create_user(
            username='hire@example.com', email='hire@example.com',
            password='Test@1234', role=User.Role.EMPLOYER,
        )
        worker_user = User.objects.create_user(
            username='worker@example.com', email='worker@example.com',
            password='Test@1234', role=User.Role.WORKER, phone='9876543210',
        )
        self.employer = EmployerProfile.objects.create(
            user=employer_user, business_name='Local Services',
        )
        self.worker = WorkerProfile.objects.create(
            user=worker_user, full_name='Aman Shaikh', mobile='9876543210',
            email='worker@example.com', village='Pune',
        )
        self.job = Job.objects.create(
            employer=self.employer, title='Electrician',
            description='Electrical maintenance and safe equipment installation.',
            status=Job.Status.ACTIVE,
        )
        self.employer_user = employer_user
        self.worker_user = worker_user

    def test_worker_consent_leads_to_hire_and_followup(self):
        self.client.force_login(self.worker_user)
        response = self.client.post(reverse('hiring:express_interest', args=[self.job.pk]))
        interest = JobInterest.objects.get(job=self.job, worker=self.worker)
        self.assertRedirects(response, reverse('workers:dashboard'))
        self.assertEqual(interest.status, JobInterest.Status.INTERESTED)
        self.assertEqual(self.client.get(response.url).status_code, 200)

        response = self.client.post(reverse('hiring:consent', args=[interest.pk]), {
            'share_name': 'on', 'share_phone': 'on', 'share_city': 'on',
        })
        self.assertRedirects(response, reverse('workers:dashboard'))
        interest.refresh_from_db()
        self.assertEqual(interest.status, JobInterest.Status.CONNECTED)
        grant = ConsentGrant.objects.get(interest=interest)
        self.assertTrue(grant.is_active)
        self.assertFalse(grant.share_phone)

        self.client.force_login(self.employer_user)
        candidates_url = reverse('hiring:job_candidates', args=[self.job.pk])
        response = self.client.get(candidates_url)
        self.assertContains(response, 'Aman Shaikh')
        self.assertContains(response, '9876543210')
        self.assertContains(response, 'href="tel:9876543210"')
        self.assertContains(response, 'href="mailto:worker%40example.com"')

        connection = Connection.objects.get(interest=interest)
        response = self.client.post(
            reverse('hiring:connection_update', args=[connection.pk]),
            {'status': Connection.Status.HIRED},
        )
        self.assertRedirects(response, candidates_url)
        connection.refresh_from_db()
        self.assertEqual(connection.status, Connection.Status.HIRED)
        self.assertEqual(FollowUp.objects.filter(connection=connection).count(), 3)
        application = JobApplication.objects.get(job=self.job, worker=self.worker)
        self.assertEqual(application.status, JobApplication.Status.HIRED)

        followup = FollowUp.objects.get(connection=connection, stage=FollowUp.Stage.DAY7)
        self.client.force_login(self.worker_user)
        response = self.client.post(reverse('hiring:followup_respond', args=[followup.pk]), {
            'payment_on_time': 'on', 'satisfaction': '5', 'comments': 'Payment was on time.',
        })
        self.assertRedirects(response, reverse('workers:dashboard'))
        self.assertTrue(FollowUpResponse.objects.filter(follow_up=followup).exists())

    def test_worker_can_decline_a_consent_request_without_sharing_data(self):
        interest = JobInterest.objects.create(
            job=self.job, worker=self.worker,
            status=JobInterest.Status.CONSENT_REQUESTED, consent_requested=True,
        )
        self.client.force_login(self.worker_user)
        response = self.client.post(
            reverse('hiring:consent', args=[interest.pk]), {'action': 'decline'},
        )
        self.assertRedirects(response, reverse('workers:dashboard'))
        interest.refresh_from_db()
        self.assertEqual(interest.status, JobInterest.Status.DECLINED)
        self.assertFalse(ConsentGrant.objects.filter(interest=interest).exists())

    def test_dashboard_no_longer_renders_sharing_requests_panel(self):
        interest = JobInterest.objects.create(
            job=self.job, worker=self.worker,
            status=JobInterest.Status.CONSENT_REQUESTED, consent_requested=True,
        )
        self.client.force_login(self.worker_user)
        response = self.client.get(reverse('workers:dashboard'))
        self.assertNotContains(response, 'Sharing requests')
        self.assertNotContains(response, reverse('hiring:consent', args=[interest.pk]))
        self.assertNotContains(response, 'consent.html')

    def test_legacy_consent_page_url_redirects_to_dashboard(self):
        interest = JobInterest.objects.create(job=self.job, worker=self.worker)
        self.client.force_login(self.worker_user)
        self.assertRedirects(
            self.client.get(reverse('hiring:consent', args=[interest.pk])),
            reverse('workers:dashboard'),
        )
