from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('',          views.index, name='index'),
    path('athlete_dash/<int:athlete_id>/', views.athlete_dash, name='athlete_dash'),
    path('athlete_dash/<int:athlete_id>/data/', views.athlete_dash_data, name='athlete_dash_data'),
    path('athlete_select/<int:comp_id>/', views.athlete_select, name='athlete_select'),

    # admin area — AdminAuthenticationForm only lets staff accounts sign in
    path('login/', auth_views.LoginView.as_view(
        template_name='ironCrawler/login.html',
        authentication_form=AdminAuthenticationForm,
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('manage/', views.manage_competitions, name='manage_competitions'),
    path('manage/<int:comp_id>/scrape/', views.toggle_competition_scrape, name='toggle_competition_scrape'),
]
