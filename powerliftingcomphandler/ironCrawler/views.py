from django.shortcuts import render, get_object_or_404
from .models import Competition, Athlete


# ── DOTS coefficients ──────────────────────────────────────────────────────
# Standard DOTS formula: dots = total * 500 / (A + B*bw + C*bw^2 + D*bw^3 + E*bw^4)
DOTS_COEFFS = {
    'male':   (-307.75076, 24.0900756, -0.1918759221, 0.0007391293, -0.000001093),
    'female': (-57.96288,  13.6175032, -0.1126655,     0.0005158568, -0.0000010706),
}


def _dots_gender(gender: str) -> str:
    """Maps the model's gender choices to the DOTS formula's male/female coefficients."""
    return 'female' if gender in ('female', 'girl', 'girls') else 'male'


def _dots_denominator(body_weight: float, gender: str) -> float:
    a, b, c, d, e = DOTS_COEFFS[_dots_gender(gender)]
    bw = body_weight
    return a + b * bw + c * bw ** 2 + d * bw ** 3 + e * bw ** 4


def total_needed_for_dots(target_dots: float, body_weight: float, gender: str) -> float:
    """Returns the total (kg) required to reach a given DOTS score at a given bodyweight."""
    return target_dots * _dots_denominator(body_weight, gender) / 500


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
 