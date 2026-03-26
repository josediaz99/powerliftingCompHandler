from django.shortcuts import render, redirect, get_object_or_404
from .models import Competition, Athlete


def index(request):
    """Main page — renders the competition list."""
    competitions = Competition.objects.all().order_by('comp_date')
 
    return render(request, 'ironCrawler/index.html', {
        'competitions': competitions,
    })


def athlete_dash(request, comp_id):
    """Athlete dashboard for a single competition."""
    competition = get_object_or_404(Competition, comp_id=comp_id)
    athletes    = competition.athletes.all()
 
    return render(request, 'ironCrawler/athlete_dash.html', {
        'competition': competition,
        'athletes':    athletes,
    })
 