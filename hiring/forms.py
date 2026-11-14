from django import forms

from .models import ConsentGrant, FollowUpResponse


class ConsentForm(forms.ModelForm):
    class Meta:
        model = ConsentGrant
        fields = (
            'share_name', 'share_city', 'share_skills', 'share_video', 'share_education',
        )
        labels = {
            'share_name': 'Name',
            'share_city': 'City / Area',
            'share_skills': 'Skills & level',
            'share_video': 'Skill video',
            'share_education': 'Education',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-check-input'


class FollowUpResponseForm(forms.ModelForm):
    class Meta:
        model = FollowUpResponse
        fields = ('payment_on_time', 'satisfaction', 'comments')
        labels = {
            'payment_on_time': 'Was the payment on time?',
            'satisfaction': 'Job satisfaction (1-5)',
            'comments': 'Anything else you want to tell us?',
        }
        widgets = {'comments': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs['class'] = 'form-check-input'
            elif isinstance(widget, forms.Select):
                widget.attrs['class'] = 'form-select'
            else:
                widget.attrs['class'] = 'form-control'
