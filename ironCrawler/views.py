from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Athlete, Competition

# admins are Django staff accounts; anyone else is sent to the login page
admin_required = staff_member_required(login_url='login')


def _competitor_pool(athlete: Athlete) -> list:
    """Returns every athlete in the given athlete's competition as plain dicts for the dashboard JS."""
    competitors = Athlete.objects.filter(competition=athlete.competition)
    return [{
        'id': c.id,
        'name': c.athlete_name,
        'gender': c.gender,
        'weight': c.weight_class,
        'division': c.division,
        'category': c.category,
        'total': c.total,
        'dots': c.dots_score or 0,
        'squat': c.best_squat,
        'bench': c.best_bench,
        'deadlift': c.best_deadlift,
    } for c in competitors]


def athlete_dash(request, athlete_id):
    """Athlete dashboard — passes full competitor pool; ranking is done client-side."""
    athlete = get_object_or_404(Athlete, pk=athlete_id)
    return render(request, 'ironCrawler/athlete_dash.html', {
        'athlete': athlete,
        'pool': _competitor_pool(athlete),
    })


def athlete_dash_data(request, athlete_id):
    """Competitor pool as JSON — polled by the dashboard so it stays current without a reload."""
    athlete = get_object_or_404(Athlete, pk=athlete_id)
    return JsonResponse({'pool': _competitor_pool(athlete)})


def index(request):
    """Main page — renders the competitions an admin has selected for scraping."""
    competitions = Competition.objects.filter(scrape_enabled=True).order_by('comp_date', 'comp_name')
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
    })


@admin_required
def manage_competitions(request):
    """Admin page — the scrape list and the competitions not on it, each earliest date first."""
    competitions = (Competition.objects
                    .annotate(athlete_count=Count('athletes'))
                    .order_by('comp_date', 'comp_name'))
    return render(request, 'ironCrawler/manage_competitions.html', {
        'scheduled': [c for c in competitions if c.scrape_enabled],
        'available': [c for c in competitions if not c.scrape_enabled],
    })


@admin_required
@require_POST
def toggle_competition_scrape(request, comp_id):
    """Adds a competition to the scrape list or removes it.

    Posts the wanted state ('enabled' = 1 or 0), so a repeat is harmless.
    """
    competition = get_object_or_404(Competition, comp_id=comp_id)
    enabled = request.POST.get('enabled') == '1'
    Competition.objects.filter(pk=competition.pk).update(scrape_enabled=enabled)
    message = (f"Added {competition.comp_name} to the scrape list" if enabled
               else f"Removed {competition.comp_name} from the scrape list")

    # the manage page's script asks for JSON; a plain form post (no JS) gets the page back
    if request.headers.get('X-Requested-With') == 'fetch':
        return JsonResponse({'comp_id': competition.pk, 'scrape_enabled': enabled, 'message': message})
    messages.success(request, message)
    return redirect('manage_competitions')
