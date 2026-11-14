from django.urls import path

from . import views

app_name = 'workers'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    # Kept as an alias so the hiring flow can still link new workers to their profile.
    path('onboarding/', views.profile_view, name='onboarding'),
    path('video/', views.upload_video, name='upload_video'),
    path('video/<int:assessment_id>/delete/', views.delete_assessment, name='delete_video'),
    path('assessments/<int:assessment_id>/', views.assessment_detail, name='assessment_detail'),
    path('assessments/<int:assessment_id>/accept-all/', views.accept_all_skills, name='accept_all_skills'),
    path('detected/<int:skill_id>/<str:decision>/', views.decide_skill, name='decide_skill'),
    path('skills/', views.skill_analysis, name='skill_analysis'),
    path('skills/<int:skill_id>/delete/', views.delete_skill, name='delete_skill'),
    path('jobs/', views.jobs, name='jobs'),
    path('jobs/<int:job_id>/apply/', views.apply_job, name='apply'),
    path('jobs/<int:job_id>/save/', views.toggle_save_job, name='save_job'),
    path('applications/', views.applications, name='applications'),
    path('applications/<int:application_id>/withdraw/', views.withdraw_application, name='withdraw'),
    path('notifications/', views.notifications, name='notifications'),
    path('settings/', views.settings, name='settings'),
]
