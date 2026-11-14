from django import forms

from accounts.validators import validate_indian_pincode, validate_not_future_date

from jobs.models import Job

from .models import EmployerProfile, Feedback

# Rule-based safety signals for the "Post a Job" check.
RISK_TERMS = [
    'registration fee', 'upfront fee', 'pay to apply', 'security deposit',
    'send money', 'bank password', 'share your otp',
]


class JobForm(forms.ModelForm):
    """Post / edit a job — validation + a rule-based suspicious-content check."""

    skills = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'e.g. farming, irrigation, teamwork'}),
        label='Skills needed',
        help_text='Separate with commas',
    )

    class Meta:
        model = Job
        fields = ('title', 'company_name', 'location', 'job_type', 'wage_min', 'wage_max', 'description')
        labels = {
            'title': 'Job title',
            'company_name': 'Business / employer name',
            'location': 'Location',
            'job_type': 'Work type',
            'wage_min': 'Monthly salary from (₹)',
            'wage_max': 'Monthly salary to (₹)',
            'description': 'Job description',
        }
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Farm Operations Assistant'}),
            'location': forms.TextInput(attrs={'placeholder': 'Village, district'}),
            'wage_min': forms.NumberInput(attrs={'min': '0'}),
            'wage_max': forms.NumberInput(attrs={'min': '0'}),
            'description': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Describe the work, schedule, and any requirements.'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.required_skills:
            self.fields['skills'].initial = ', '.join(str(s) for s in self.instance.required_skills)

    def clean(self):
        cleaned = super().clean()
        title = (cleaned.get('title') or '').strip()
        location = (cleaned.get('location') or '').strip()
        description = (cleaned.get('description') or '').strip()
        skills = [s.strip() for s in (cleaned.get('skills') or '').split(',') if s.strip()]
        wage_min, wage_max = cleaned.get('wage_min'), cleaned.get('wage_max')

        if len(title) < 4:
            self.add_error('title', 'Add a clear job title (at least 4 characters).')
        if len(location) < 2:
            self.add_error('location', 'Add the job location.')
        if len(description) < 25:
            self.add_error('description', 'Describe the role in 25 or more characters.')
        if not skills:
            self.add_error('skills', 'Add at least one skill.')
        if wage_min and wage_max and wage_min > wage_max:
            self.add_error('wage_max', 'The highest amount must be at least the starting amount.')

        # Rule-based safety check (clearly labelled as not AI on the page).
        haystack = f'{title} {description}'.lower()
        risky = next((term for term in RISK_TERMS if term in haystack), None)
        if risky:
            raise forms.ValidationError(
                f'This rule-based safety check flagged “{risky}”. Remove requests for fees, '
                'deposits, or sensitive account details and review the job description.'
            )

        cleaned['skills_list'] = skills
        return cleaned

    def save(self, commit=True):
        job = super().save(commit=False)
        job.required_skills = self.cleaned_data['skills_list']
        if not job.company_name:
            job.company_name = job.employer.business_name
        if commit:
            job.save()
        return job


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ('milestone', 'rating', 'notes')
        labels = {
            'milestone': 'Follow-up milestone',
            'rating': 'Job satisfaction',
            'notes': 'Notes',
        }
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 4, 'placeholder': 'How is the role going? Any support needed?'}),
        }


class EmployerSettingsForm(forms.ModelForm):
    class Meta:
        model = EmployerProfile
        fields = (
            'business_name', 'business_type', 'contact_name', 'contact_date_of_birth',
            'city', 'state', 'pincode', 'address', 'description', 'job_alerts',
        )
        labels = {
            'business_name': 'Business / employer name',
            'business_type': 'Business type',
            'contact_name': 'Contact person',
            'contact_date_of_birth': 'Contact person date of birth',
            'city': 'City',
            'state': 'State',
            'pincode': 'PIN code',
            'address': 'Address',
            'description': 'Business description',
            'job_alerts': 'Show job and application updates',
        }
        widgets = {
            'contact_date_of_birth': forms.DateInput(attrs={'type': 'date', 'autocomplete': 'bday'}),
            'pincode': forms.TextInput(attrs={'inputmode': 'numeric', 'maxlength': '6', 'autocomplete': 'postal-code'}),
            'address': forms.TextInput(attrs={'autocomplete': 'street-address'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_contact_date_of_birth(self):
        value = self.cleaned_data.get('contact_date_of_birth')
        validate_not_future_date(value)
        return value

    def clean_pincode(self):
        value = (self.cleaned_data.get('pincode') or '').strip()
        validate_indian_pincode(value)
        return value
