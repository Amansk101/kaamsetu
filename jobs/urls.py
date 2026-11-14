from django.urls import path

from . import views

app_name = 'jobs'

urlpatterns = [
    path('new/', views.post_job, name='post_job'),
    path('<int:pk>/', views.job_detail, name='detail'),
]
