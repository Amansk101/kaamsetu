from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('home/', views.landing, name='home'),
    path('select-role/', views.select_role, name='select_role'),
    path('go/', views.go, name='go'),
    path('how-it-works/', views.how_it_works, name='how_it_works'),
    path('about/', views.about, name='about'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('i18n/set-language/', views.set_language, name='set_language'),
]
