from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import RegisterForm, StrongSetPasswordForm
from employers.models import EmployerProfile
from workers.models import WorkerProfile


class RegistrationValidationTests(TestCase):
    def form_data(self, **overrides):
        data = {
            'role': 'worker',
            'full_name': 'Aman Shaikh',
            'email': 'aman@example.com',
            'mobile': '9876543210',
            'password': 'Aman@123',
            'confirm_password': 'Aman@123',
            'terms': 'on',
        }
        data.update(overrides)
        return data

    def test_valid_registration_data(self):
        self.assertTrue(RegisterForm(self.form_data()).is_valid())

    def test_worker_signup_page_uses_real_form_and_creates_worker_profile(self):
        page = self.client.get(reverse('accounts:register'), {'role': 'worker'})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Join KaamSetu Today')
        self.assertContains(page, 'auth-visual')
        response = self.client.post(reverse('accounts:register') + '?role=worker', {
            **self.form_data(), 'date_of_birth': '1995-06-15', 'city': 'Pune',
            'state': 'Maharashtra', 'pincode': '411001',
        })
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(email='aman@example.com')
        self.assertEqual(user.role, 'worker')
        profile = WorkerProfile.objects.get(user=user)
        self.assertEqual(profile.village, 'Pune')
        self.assertEqual(profile.pincode, '411001')
        self.assertEqual(str(profile.date_of_birth), '1995-06-15')

    def test_employer_signup_creates_employer_profile_and_preserves_role(self):
        response = self.client.post(reverse('accounts:register') + '?role=employer', {
            **self.form_data(role='employer', email='owner@example.com', mobile='9876543211'),
            'company_name': 'Pune Workshop', 'city': 'Pune', 'state': 'Maharashtra',
            'pincode': '411001',
        })
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(email='owner@example.com')
        self.assertEqual(user.role, 'employer')
        profile = EmployerProfile.objects.get(user=user)
        self.assertEqual(profile.business_name, 'Pune Workshop')
        self.assertEqual(profile.city, 'Pune')
        self.assertEqual(profile.pincode, '411001')

    def test_name_rejects_invalid_characters_and_whitespace(self):
        for name in ('12345', 'Aman123', 'Aman@Shaikh', '   ', 'Aman  Shaikh', ' Aman', 'Aman '):
            with self.subTest(name=name):
                form = RegisterForm(self.form_data(full_name=name))
                self.assertFalse(form.is_valid())
                self.assertIn('full_name', form.errors)

    def test_names_support_indian_scripts_and_common_name_punctuation(self):
        for name in ('अमित कुमार', 'शिवानी पाटील', 'O’Neil', 'Mary-Jane'):
            with self.subTest(name=name):
                form = RegisterForm(self.form_data(full_name=name))
                self.assertTrue(form.is_valid(), form.errors)

    def test_mobile_and_password_rules(self):
        invalid_mobiles = (
            '1234567890', '987654321', '98765432101', '98765abc10', '98765@3210',
            ' 9876543210', '9876543210 ', '98765 43210',
        )
        for mobile in invalid_mobiles:
            with self.subTest(mobile=mobile):
                self.assertFalse(RegisterForm(self.form_data(mobile=mobile)).is_valid())

        weak_password = RegisterForm(self.form_data(password='aman1234', confirm_password='aman1234'))
        self.assertFalse(weak_password.is_valid())
        self.assertIn('password', weak_password.errors)

    def test_email_rejects_whitespace_and_normalizes_case(self):
        valid = RegisterForm(self.form_data(email='Aman@Example.com'))
        self.assertTrue(valid.is_valid())
        self.assertEqual(valid.cleaned_data['email'], 'aman@example.com')

        for email in (' aman@example.com', 'aman@example.com ', 'aman @example.com'):
            with self.subTest(email=email):
                form = RegisterForm(self.form_data(email=email))
                self.assertFalse(form.is_valid())
                self.assertIn('email', form.errors)

    def test_duplicate_email_and_mobile_are_rejected(self):
        User = get_user_model()
        User.objects.create_user(
            username='existing@example.com', email='existing@example.com', phone='9123456789',
            password='Existing@123',
        )
        form = RegisterForm(self.form_data(email='EXISTING@example.com', mobile='9123456789'))
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
        self.assertIn('mobile', form.errors)

    def test_database_enforces_case_insensitive_email_uniqueness(self):
        User = get_user_model()
        User.objects.create_user(
            username='first@example.com', email='First@Example.com', password='Existing@123'
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(
                username='second@example.com', email='first@example.com', password='Existing@123'
            )


class PasswordSecurityTests(TestCase):
    def test_new_password_uses_the_shared_strong_password_policy(self):
        user = get_user_model().objects.create_user(
            username='worker@example.com', email='worker@example.com', password='Existing@123'
        )
        form = StrongSetPasswordForm(user, {
            'new_password1': 'weakpass', 'new_password2': 'weakpass',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('new_password2', form.errors)

    def test_login_accepts_existing_password_without_new_complexity_rules(self):
        user = get_user_model().objects.create_user(
            username='legacy@example.com', email='legacy@example.com',
            password='legacy12', role='worker',
        )
        response = self.client.post(reverse('accounts:login') + '?role=worker', {
            'role': 'worker', 'email': 'LEGACY@example.com', 'password': 'legacy12',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('core:go'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_invalid_login_uses_generic_credentials_message(self):
        response = self.client.post(reverse('accounts:login') + '?role=worker', {
            'role': 'worker', 'email': 'unknown@example.com', 'password': 'wrong',
        })
        self.assertContains(response, 'Wrong email or password. Please check and try again.')
        self.assertNotContains(response, 'No account exists')

    def test_homepage_uses_static_hero_artwork_without_background_video(self):
        response = self.client.get(reverse('core:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="hero-poster"')
        self.assertContains(response, 'skilled-trades-team.webp')
        self.assertNotContains(response, '<video')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_reset_request_does_not_reveal_whether_email_exists(self):
        User = get_user_model()
        User.objects.create_user(
            username='worker@example.com', email='worker@example.com', password='Existing@123'
        )
        response = self.client.post(reverse('accounts:password_reset'), {'email': 'unknown@example.com'})
        self.assertRedirects(response, reverse('accounts:password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

        response = self.client.post(reverse('accounts:password_reset'), {'email': 'worker@example.com'})
        self.assertRedirects(response, reverse('accounts:password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
