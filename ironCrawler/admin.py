from django.contrib import admin

from .models import Athlete, Competition


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ('comp_name', 'comp_date', 'scrape_enabled')
    list_editable = ('scrape_enabled',)
    list_filter = ('scrape_enabled', 'comp_date')
    search_fields = ('comp_name',)
    ordering = ('comp_date', 'comp_name')


@admin.register(Athlete)
class AthleteAdmin(admin.ModelAdmin):
    list_display = ('athlete_name', 'competition', 'weight_class', 'total')
    search_fields = ('athlete_name',)
