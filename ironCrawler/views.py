from django.shortcuts import get_object_or_404, render

from .models import Athlete, Competition


def athlete_dash(request, athlete_id):
    """Athlete dashboard — passes full competitor pool; ranking is done client-side."""
    athlete = get_object_or_404(Athlete, pk=athlete_id)
    competitors = Athlete.objects.filter(competition=athlete.competition)
    return render(request, 'ironCrawler/athlete_dash.html', {
        'athlete': athlete,
        'competitors': competitors,
    })


def index(request):
    """Main page — renders the competition list."""
    competitions = Competition.objects.all().order_by('comp_date')
    return render(request, 'ironCrawler/index.html', {
        'competitions': competitions,
    })


def athlete_select(request, comp_id):
    """Athlete selection — passes full roster; filtering and sorting are done client-side."""
    competition = get_object_or_404(Competition, comp_id=comp_id)
    athletes = competition.athletes.order_by('athlete_name')
    return render(request, 'ironCrawler/athlete_select.html', {
        'competition': competition,
        'athletes': athletes,
        'can_select': True,
    })
 