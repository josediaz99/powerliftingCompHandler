from django.db import models

class Competition(models.Model):
    comp_id   = models.AutoField(primary_key=True)
    comp_name = models.CharField(max_length=255)
    comp_url  = models.URLField()
    comp_date = models.DateField()

    class Meta:
        unique_together = ('comp_name', 'comp_date')

    def __str__(self):
        return f"{self.comp_name} ({self.comp_date})"


class Athlete(models.Model):
    GENDER_CHOICES = [
        ('male',   'Male'),
        ('female', 'Female'),
        ('boy',    'Boy'),
        ('girl',   'Girl'),
        ('boys',   'Boys'),
        ('girls',  'Girls'),
    ]
    EQUIPMENT_CHOICES = [
        ('raw',       'Raw'),
        ('equipped',  'Equipped'),
    ]

    competition  = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name='athletes', null=True, blank=True)
    athlete_name = models.CharField(max_length=100)
    gender       = models.CharField(max_length=10, choices=GENDER_CHOICES)
    category     = models.CharField(max_length=20, blank=True, choices=EQUIPMENT_CHOICES)
    team         = models.CharField(max_length=50, blank=True)
    division     = models.CharField(max_length=50, blank=True)  # award division
    weight_class = models.CharField(max_length=10, blank=True)
    age          = models.IntegerField(null=True, blank=True)   # exact age

    def __str__(self):
        return self.athlete_name