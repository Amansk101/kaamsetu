from django.urls import path

from . import views

app_name = 'hiring'

urlpatterns = [
    path('interest/<int:job_id>/', views.express_interest, name='express_interest'),
    path('consent/<int:interest_id>/', views.consent, name='consent'),
    path('job/<int:job_id>/candidates/', views.job_candidates, name='job_candidates'),
    path('connection/<int:pk>/update/', views.connection_update, name='connection_update'),
    path('request-consent/<int:worker_id>/', views.request_consent, name='request_consent'),
    path('followup/<int:pk>/respond/', views.followup_respond, name='followup_respond'),
]
