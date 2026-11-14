from django import forms
from pathlib import Path

from accounts.validators import (
    validate_indian_mobile, validate_indian_pincode, validate_name,
    validate_not_future_date,
)
from core.models import Skill

from .models import SkillAssessment, WorkerProfile


class WorkerProfileForm(forms.ModelForm):
    """Worker profile create/edit — mirrors the React *CreateProfile* page."""

    mobile = forms.CharField(
        required=False, strip=False, max_length=15,
        widget=forms.TextInput(attrs={
            'type': 'tel', 'autocomplete': 'tel', 'inputmode': 'numeric',
            'maxlength': '10', 'placeholder': '9876543210',
        }),
    )
    skills = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'e.g. cooking, tailoring, electrical work'}),
        label='Skills',
        help_text='Separate with commas',
    )

    class Meta:
        model = WorkerProfile
        fields = (
            'full_name', 'date_of_birth', 'gender', 'mobile', 'email', 'photo',
            'village', 'taluka', 'district', 'state', 'pincode',
            'education_level', 'school', 'qualification',
            'experience', 'preferred_job', 'expected_salary', 'availability',
        )
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'gender': forms.Select(),
            'mobile': forms.TextInput(attrs={'type': 'tel'}),
            'email': forms.EmailInput(),
            'pincode': forms.TextInput(attrs={'inputmode': 'numeric', 'maxlength': '6'}),
            'expected_salary': forms.NumberInput(attrs={'min': '0'}),
            'photo': forms.FileInput(attrs={
                'accept': '.jpg,.jpeg,.png', 'data-photo-input': '',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['full_name'].widget.attrs['data-validate'] = 'name'
        self.fields['mobile'].widget.attrs['data-validate'] = 'mobile-optional'
        if self.instance and self.instance.pk:
            self.fields['skills'].initial = self.instance.skills_text
        for name, field in self.fields.items():
            if name == 'skills':
                continue
            field.widget.attrs.setdefault('placeholder', '')

    def save(self, commit=True):
        profile = super().save(commit=commit)
        if commit:
            self.save_skills()
        return profile

    def clean_full_name(self):
        value = self.cleaned_data.get('full_name') or ''
        validate_name(value)
        if len(value) < 2:
            raise forms.ValidationError('Please enter your name (at least 2 characters).')
        return value.strip()

    def clean_mobile(self):
        value = self.cleaned_data.get('mobile') or ''
        if value:
            validate_indian_mobile(value)
        return value

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if not photo or self.files.get(self.add_prefix('photo')) is None:
            return photo
        if photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Choose a profile photo smaller than 5 MB.')
        suffix = Path(photo.name).suffix.lower()
        if suffix not in {'.jpg', '.jpeg', '.png'}:
            raise forms.ValidationError('Choose a JPG or PNG profile photo.')
        header = photo.read(8)
        photo.seek(0)
        is_jpeg = header.startswith(b'\xff\xd8\xff')
        is_png = header == b'\x89PNG\r\n\x1a\n'
        if (suffix in {'.jpg', '.jpeg'} and not is_jpeg) or (suffix == '.png' and not is_png):
            raise forms.ValidationError('The selected file is not a valid JPG or PNG image.')
        return photo

    def save_skills(self):
        """Sync the comma separated ``skills`` text into WorkerSkill rows.

        Existing rows are kept (so AI-verified levels and confidence are not
        lost) — only the skills the worker actually removed are deleted.
        """
        names = [part.strip() for part in (self.cleaned_data.get('skills') or '').split(',')]
        names = [name for name in names if name]
        from .models import WorkerSkill

        existing = {
            ws.skill.name.strip().lower(): ws
            for ws in self.instance.skills.select_related('skill')
        }
        keep_ids = []
        for name in names:
            ws = existing.get(name.lower())
            if ws is None:
                skill, _ = Skill.objects.get_or_create(name=name)
                ws = WorkerSkill.objects.create(worker=self.instance, skill=skill)
            keep_ids.append(ws.pk)
        WorkerSkill.objects.filter(worker=self.instance).exclude(pk__in=keep_ids).delete()

    def clean_date_of_birth(self):
        value = self.cleaned_data.get('date_of_birth')
        validate_not_future_date(value)
        return value

    def clean_pincode(self):
        value = (self.cleaned_data.get('pincode') or '').strip()
        validate_indian_pincode(value)
        return value


class SkillVideoForm(forms.ModelForm):
    """Skills video upload (stored via Django media settings)."""

    class Meta:
        model = SkillAssessment
        fields = ('video',)
        labels = {
            'video': 'Skill video',
        }
        widgets = {
            # Plain file input — any extension/type is accepted. Frontend JS
            # hooks this ``data-video-input`` attribute for the preview + drop.
            'video': forms.FileInput(attrs={
                'data-video-input': '',
                'accept': '.mp4,.mov,.webm,.mkv,.avi,.m4v,.3gp,.ogv,video/*',
            }),
        }

    def clean_video(self):
        video = self.cleaned_data.get('video')
        if video and getattr(video, 'size', 0) > 100 * 1024 * 1024:
            raise forms.ValidationError('Please choose a video smaller than 100 MB.')
        if video:
            allowed = {'.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v', '.3gp', '.ogv'}
            suffix = Path(video.name).suffix.lower()
            if suffix not in allowed:
                raise forms.ValidationError(
                    'Choose a supported video file (MP4, MOV, WebM, MKV, AVI, M4V, 3GP or OGV).'
                )
            header = video.read(16)
            video.seek(0)
            valid_container = (
                (suffix in {'.mp4', '.mov', '.m4v', '.3gp'} and header[4:8] == b'ftyp')
                or (suffix in {'.webm', '.mkv'} and header.startswith(b'\x1a\x45\xdf\xa3'))
                or (suffix == '.avi' and header.startswith(b'RIFF') and header[8:12] == b'AVI ')
                or (suffix == '.ogv' and header.startswith(b'OggS'))
            )
            if not valid_container:
                raise forms.ValidationError(
                    'The selected file does not appear to be a valid video in the chosen format.'
                )
        return video


class WorkerSettingsForm(forms.ModelForm):
    class Meta:
        model = WorkerProfile
        fields = ('job_alerts', 'nearby_only', 'profile_visible', 'preferred_job_type', 'minimum_salary')
        labels = {
            'profile_visible': 'Allow employers to find and view my profile',
            'nearby_only': 'Prioritize opportunities near my location',
            'job_alerts': 'Show job and application updates',
            'preferred_job_type': 'Preferred job type',
            'minimum_salary': 'Minimum monthly salary (₹)',
        }
        widgets = {
            'preferred_job_type': forms.Select(choices=[
                ('', 'Any type'),
                ('full_time', 'Full time'),
                ('part_time', 'Part time'),
                ('seasonal', 'Seasonal'),
                ('contract', 'Contract'),
            ]),
            'minimum_salary': forms.NumberInput(attrs={'min': '0'}),
        }
