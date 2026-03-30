from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Q
from .models import Competition, Athlete


def index(request):
    """Main page — renders the competition list."""
    competitions = Competition.objects.all().order_by('comp_date')
 
    return render(request, 'ironCrawler/index.html', {
        'competitions': competitions,
    })


def athlete_select(request, comp_id):
    """Athlete selection for a single competition."""
    competition = get_object_or_404(Competition, comp_id=comp_id)
    
    # Get filter parameters
    sort_by = request.GET.get('sort', 'name')  # 'name' or '-name'
    gender_filter = request.GET.get('gender', '')
    category_filter = request.GET.get('category', '')
    division_filter = request.GET.get('division', '')
    weight_class_filter = request.GET.get('weight_class', '')
    
    # Start with all athletes for this competition
    athletes = competition.athletes.all()
    
    # Apply filters
    if gender_filter:
        athletes = athletes.filter(gender__iexact=gender_filter)
    if category_filter:
        athletes = athletes.filter(category__iexact=category_filter)
    if division_filter:
        athletes = athletes.filter(division__iexact=division_filter)
    if weight_class_filter:
        athletes = athletes.filter(weight_class__iexact=weight_class_filter)
    
    # Apply sorting
    if sort_by == 'name':
        athletes = athletes.order_by('athlete_name')
    elif sort_by == '-name':
        athletes = athletes.order_by('-athlete_name')
    
    # Get distinct values for filter dropdowns
    all_athletes = competition.athletes.all()
    genders = sorted(set(a.gender for a in all_athletes if a.gender))
    categories = sorted(set(a.category for a in all_athletes if a.category))
    divisions = sorted(set(a.division for a in all_athletes if a.division))
    weight_classes = sorted(set(a.weight_class for a in all_athletes if a.weight_class))
 
    return render(request, 'ironCrawler/athlete_select.html', {
        'competition': competition,
        'athletes': athletes,
        'can_select': True,
        'sort_by': sort_by,
        'filters': {
            'gender': gender_filter,
            'category': category_filter,
            'division': division_filter,
            'weight_class': weight_class_filter,
        },
        'filter_options': {
            'genders': genders,
            'categories': categories,
            'divisions': divisions,
            'weight_classes': weight_classes,
        },
    })
 