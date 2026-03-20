from django.shortcuts import render, redirect, get_object_or_404
from .models import Competition, Athlete


def index(request):
    """Main page — renders the competition list."""
    competitions = Competition.objects.all().order_by('comp_date')

    return render(request, 'competitions/index.html', {
        'competitions': competitions,
    })

def athlete_dash(request, comp_id):
    # retrieve athletes from database using comp_id
    competition = get_object_or_404(Competition, id=comp_id)
    athletes = competition.athletes.all()
    # TODO: calculate extra stats for each athlete

    return redirect('competitions/athlete_dash', athletes=athletes)