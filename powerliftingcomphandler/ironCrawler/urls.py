from django.urls import path
from . import views

urlpatterns = [
    path('',          views.index, name='index'),
    path('athlete_dash/<int:comp_id>/', views.athlete_dash, name='athlete_dash'),
]