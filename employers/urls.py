from django.urls import path

from . import views

app_name = 'employers'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('jobs/new/', views.post_job, name='post_job'),
    path('jobs/', views.jobs, name='jobs'),
    path('jobs/<int:job_id>/', views.job_detail, name='job_detail'),
    path('jobs/<int:job_id>/edit/', views.edit_job, name='edit_job'),
    path('jobs/<int:job_id>/close/', views.close_job, name='close_job'),
    path('workers/', views.workers, name='workers'),
    path('workers/<int:worker_id>/', views.worker_detail, name='worker_detail'),
    path('applications/', views.applications, name='applications'),
    path('applications/<int:application_id>/status/', views.update_application_status, name='update_status'),
    path('hired/', views.hired, name='hired'),
    path('feedback/', views.feedback, name='feedback'),
    path('notifications/', views.notifications, name='notifications'),
    path('settings/', views.settings, name='settings'),
]
