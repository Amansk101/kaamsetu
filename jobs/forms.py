from django import forms


class JobPostForm(forms.Form):
    raw_description = forms.CharField(
        label='Job details (type it, or paste the text of a voice note)',
        widget=forms.Textarea(
            attrs={
                'rows': 4,
                'class': 'form-control',
                'placeholder': 'I need 2 plumbers, 800-1000 rupees per day, in Dhanbad. Should join immediately.',
            }
        ),
    )
