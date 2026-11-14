"""Skill-assessment workflow tests.

These run entirely offline: the Gemini vision call is mocked, so no real API
call is ever made. They cover the dynamic multi-skill discovery, the
evidence rules (no score for claimed/unseen work), the worker approval flow
and the employer visibility rules.
"""
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from agents.logic import assess_skill_video
from employers.models import EmployerProfile
from jobs.models import Job
from workers.models import DetectedSkill, SkillAssessment, WorkerProfile, WorkerSkill
from workers.forms import SkillVideoForm, WorkerProfileForm

User = get_user_model()

FAKE_VISION = {
    'provider': 'gemini',
    'model': 'gemini-2.5-flash',
    'profession': 'Cooking',
    'profession_confidence': 0.9,
    'work_summary': 'Chopping vegetables and cooking.',
    'overall_summary': 'Clear knife work was demonstrated.',
    'skills': [
        {
            'name': 'Knife Handling', 'description': 'Slicing onions', 'category': 'Cooking',
            'score': 78, 'level': 'advanced', 'confidence': 0.8,
            'reason': 'Even slices, controlled motion.',
            'strengths': ['Steady hand'], 'improvements': ['Work a little slower'],
            'recommendations': ['Practise julienne cuts'],
            'evidence': ['00:12 slicing onions evenly'],
            'limitations': '', 'evidence_status': 'observed',
        },
        {
            'name': 'Plating', 'description': '', 'category': 'Cooking',
            'score': None, 'level': '', 'confidence': 0.4,
            'reason': 'Only mentioned, never shown.',
            'strengths': [], 'improvements': [], 'recommendations': [], 'evidence': [],
            'limitations': 'The plate was never visible.', 'evidence_status': 'claimed',
        },
    ],
    'insufficient_notes': ['Plating could not be judged.'],
    'has_speech': True,
    'transcript': 'I am cooking onions.',
    'speech_language': 'Hindi',
    'speech_quality': 'clear',
    'speech_correct': True,
    'speech_feedback': 'Your explanation matched the work.',
}


class ReportBuilderTests(TestCase):
    """The report builders must never invent a rating."""

    def test_ai_report_scores_only_observed_skills(self):
        report = assess_skill_video(42, 'beginner', '', filename='video.mp4', vision=FAKE_VISION)
        self.assertEqual(report['source'], 'ai')
        self.assertTrue(report['is_ai'])
        self.assertEqual(report['profession'], 'Cooking')
        self.assertEqual(report['overall'], 78)
        self.assertEqual(report['level'], 'skilled')
        self.assertEqual(report['skill_count'], 2)
        self.assertEqual(report['assessable_count'], 1)

        by_name = {row['name']: row for row in report['skills']}
        self.assertTrue(by_name['Knife Handling']['is_assessable'])
        self.assertEqual(by_name['Knife Handling']['score'], 78)
        self.assertEqual(by_name['Knife Handling']['profile_level'], 'skilled')
        # Claimed work carries no score and no level.
        self.assertFalse(by_name['Plating']['is_assessable'])
        self.assertIsNone(by_name['Plating']['score'])
        self.assertEqual(by_name['Plating']['level'], '')
        self.assertIn('Plating: claimed only — no score was given.', report['insufficient_notes'])

    def test_rule_based_fallback_never_scores(self):
        report = assess_skill_video(20, 'beginner', '', filename='cooking_demo.mp4')
        self.assertEqual(report['source'], 'rule_based')
        self.assertFalse(report['is_ai'])
        self.assertEqual(report['overall'], 0)
        self.assertEqual(report['level'], '')
        self.assertEqual(report['assessable_count'], 0)
        self.assertEqual(report['skills'][0]['name'], 'Cook')
        self.assertIsNone(report['skills'][0]['score'])

    def test_malformed_vision_output_does_not_break(self):
        report = assess_skill_video(10, 'beginner', '', filename='x.mp4', vision={'skills': 'nonsense'})
        self.assertEqual(report['source'], 'rule_based')
        self.assertEqual(report['skills'], [])


class ApprovalFlowTests(TestCase):
    """Upload -> detected skills -> worker approval -> employer visibility."""

    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix='ks-test-media-')
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    def setUp(self):
        self.worker_user = User.objects.create_user(
            username='worker1', password='test-pass-123', role=User.Role.WORKER,
        )
        self.profile = WorkerProfile.objects.create(user=self.worker_user, full_name='Ravi Kumar')
        self.client.force_login(self.worker_user)

    def test_profile_form_accepts_indian_script_names_and_optional_mobile(self):
        form = WorkerProfileForm({
            'full_name': 'अमित कुमार', 'mobile': '', 'email': 'amit@example.com',
            'availability': WorkerProfile.Availability.IMMEDIATE,
        }, instance=self.profile)
        self.assertTrue(form.is_valid(), form.errors)

        invalid_mobile = WorkerProfileForm({
            'full_name': 'अमित कुमार', 'mobile': ' 9876543210 ',
            'email': 'amit@example.com',
            'availability': WorkerProfile.Availability.IMMEDIATE,
        }, instance=self.profile)
        self.assertFalse(invalid_mobile.is_valid())
        self.assertIn('mobile', invalid_mobile.errors)

    def test_profile_photo_rejects_files_that_only_claim_an_image_extension(self):
        photo = SimpleUploadedFile('profile.jpg', b'not an image', content_type='image/jpeg')
        form = WorkerProfileForm({
            'full_name': 'Ravi Kumar', 'mobile': '', 'email': 'ravi@example.com',
            'availability': WorkerProfile.Availability.IMMEDIATE,
        }, {'photo': photo}, instance=self.profile)
        self.assertFalse(form.is_valid())
        self.assertIn('photo', form.errors)

    def test_profile_page_includes_photo_preview_and_feedback_hooks(self):
        response = self.client.get('/worker/profile/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-photo-input')
        self.assertContains(response, 'data-photo-avatar')
        self.assertContains(response, 'data-photo-feedback')

    def test_assessment_report_renders_full_video_player(self):
        assessment = SkillAssessment.objects.create(
            worker=self.profile, video='skill_videos/worker-demo.mp4',
        )
        response = self.client.get(f'/worker/assessments/{assessment.pk}/')
        self.assertContains(response, 'controls playsinline preload="metadata"')
        self.assertContains(response, 'skill_videos/worker-demo.mp4')

    def test_skill_video_rejects_a_fake_mp4_extension(self):
        upload = SimpleUploadedFile('demo.mp4', b'not a video', content_type='video/mp4')
        form = SkillVideoForm({}, {'video': upload})
        self.assertFalse(form.is_valid())
        self.assertIn('video', form.errors)

    def test_skill_video_accepts_a_valid_mp4_container_header(self):
        upload = SimpleUploadedFile(
            'demo.mp4', b'\x00\x00\x00\x18ftypisom' + b'\x00' * 32,
            content_type='video/mp4',
        )
        form = SkillVideoForm({}, {'video': upload})
        self.assertTrue(form.is_valid(), form.errors)

    def test_dashboard_renders_real_empty_states_and_role_navigation(self):
        response = self.client.get('/worker/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Application progress')
        self.assertContains(response, 'No application activity yet')
        self.assertContains(response, 'AI Skill Analysis')
        self.assertContains(response, 'videos/kaamsetu-worker-dashboard.mp4')
        self.assertContains(response, 'skilled-trades-team.webp')

    def test_dashboard_recommendation_uses_real_job_fields_and_details_control(self):
        employer_user = User.objects.create_user(
            username='market@example.com', password='test-pass-123', role=User.Role.EMPLOYER,
        )
        employer = EmployerProfile.objects.create(user=employer_user, business_name='Market Works')
        Job.objects.create(
            employer=employer, title='Electrician', company_name='Market Works',
            location='Pune', required_skills=['Wiring', 'Safety testing'],
            wage_min=18000, wage_max=22000, wage_period=Job.WagePeriod.MONTH,
            job_type=Job.JobType.FULL_TIME, status=Job.Status.ACTIVE,
        )
        response = self.client.get('/worker/dashboard/')
        for content in ('Electrician', 'Market Works', 'Pune', 'Full time', 'Wiring', 'Safety testing', 'View Details'):
            self.assertContains(response, content)

    def _upload(self, name='demo.mp4'):
        video = SimpleUploadedFile(name, b'\x00\x00\x00\x18ftypisom' + b'x' * 2048, content_type='video/mp4')
        return self.client.post('/worker/video/', {'video': video}, follow=False)

    def test_upload_stores_pending_skills_without_touching_profile(self):
        with patch('workers.views.vision_ai.is_enabled', return_value=True), \
                patch('workers.views.vision_ai.analyze', return_value=FAKE_VISION):
            response = self._upload()
        self.assertEqual(response.status_code, 302)

        assessment = SkillAssessment.objects.get(worker=self.profile)
        self.assertEqual(assessment.analysis_source, SkillAssessment.Source.AI)
        self.assertEqual(assessment.detected_profession, 'Cooking')
        self.assertEqual(assessment.ai_model, 'gemini-2.5-flash')

        detected = assessment.detected_skills.all()
        self.assertEqual(detected.count(), 2)
        self.assertTrue(all(d.approval_status == DetectedSkill.Approval.PENDING for d in detected))
        # Nothing is published to the profile before the worker approves it.
        self.assertFalse(WorkerSkill.objects.filter(worker=self.profile).exists())

    def test_accept_publishes_skill_and_reject_keeps_it_hidden(self):
        with patch('workers.views.vision_ai.is_enabled', return_value=True), \
                patch('workers.views.vision_ai.analyze', return_value=FAKE_VISION):
            self._upload()

        assessment = SkillAssessment.objects.get(worker=self.profile)
        knife = assessment.detected_skills.get(name='Knife Handling')
        plating = assessment.detected_skills.get(name='Plating')

        self.client.post(f'/worker/detected/{knife.pk}/accept/')
        self.client.post(f'/worker/detected/{plating.pk}/reject/')

        knife.refresh_from_db()
        plating.refresh_from_db()
        self.assertEqual(knife.approval_status, DetectedSkill.Approval.ACCEPTED)
        self.assertEqual(plating.approval_status, DetectedSkill.Approval.REJECTED)

        published = WorkerSkill.objects.filter(worker=self.profile).select_related('skill')
        self.assertEqual([ws.skill.name for ws in published], ['Knife Handling'])
        self.assertEqual(published[0].level, 'skilled')
        self.assertTrue(published[0].verified)

    def test_accept_all_only_accepts_rated_skills(self):
        with patch('workers.views.vision_ai.is_enabled', return_value=True), \
                patch('workers.views.vision_ai.analyze', return_value=FAKE_VISION):
            self._upload()
        assessment = SkillAssessment.objects.get(worker=self.profile)

        self.client.post(f'/worker/assessments/{assessment.pk}/accept-all/')

        accepted = set(
            assessment.detected_skills
            .filter(approval_status=DetectedSkill.Approval.ACCEPTED)
            .values_list('name', flat=True)
        )
        self.assertEqual(accepted, {'Knife Handling'})

    def test_history_keeps_every_assessment(self):
        with patch('workers.views.vision_ai.is_enabled', return_value=True), \
                patch('workers.views.vision_ai.analyze', return_value=FAKE_VISION):
            self._upload('first.mp4')
            self._upload('second.mp4')
        self.assertEqual(SkillAssessment.objects.filter(worker=self.profile).count(), 2)

    def test_employer_sees_only_accepted_skills(self):
        with patch('workers.views.vision_ai.is_enabled', return_value=True), \
                patch('workers.views.vision_ai.analyze', return_value=FAKE_VISION):
            self._upload()
        assessment = SkillAssessment.objects.get(worker=self.profile)
        knife = assessment.detected_skills.get(name='Knife Handling')
        plating = assessment.detected_skills.get(name='Plating')
        self.client.post(f'/worker/detected/{knife.pk}/accept/')
        self.client.post(f'/worker/detected/{plating.pk}/accept/')
        # Drain the worker's flash messages (they belong to the worker, not the
        # employer whose page we open next).
        self.client.get(f'/worker/assessments/{assessment.pk}/')

        employer_user = User.objects.create_user(
            username='boss1', password='test-pass-123', role=User.Role.EMPLOYER,
        )
        EmployerProfile.objects.create(user=employer_user, business_name='Sharma Kirana')
        self.client.force_login(employer_user)

        response = self.client.get(f'/employer/workers/{self.profile.pk}/')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('Knife Handling', body)
        self.assertIn('78', body)
        # The skill without visual evidence is never exposed to employers.
        self.assertNotIn('Plating', body)

    def test_rule_based_upload_still_records_assessment(self):
        with patch('workers.views.vision_ai.is_enabled', return_value=True), \
                patch('workers.views.vision_ai.analyze', return_value=None):
            self._upload('no_ai.mp4')
        assessment = SkillAssessment.objects.get(worker=self.profile)
        self.assertEqual(assessment.analysis_source, SkillAssessment.Source.RULE_BASED)
        self.assertEqual(assessment.detected_skills.count(), 0)
        self.assertFalse(WorkerSkill.objects.filter(worker=self.profile).exists())
