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
        ('male',   'MALE'),
        ('female', 'FEMALE'),
    ]

    competition  = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name='athletes', null=True, blank=True)
    athlete_name = models.CharField(max_length=255)
    gender       = models.CharField(max_length=6, choices=GENDER_CHOICES)
    category     = models.CharField(max_length=100, blank=True)
    team         = models.CharField(max_length=100, blank=True)
    session      = models.CharField(max_length=100, blank=True)
    flight       = models.CharField(max_length=100, blank=True)
    division     = models.CharField(max_length=100, blank=True)
    bw           = models.FloatField(null=True, blank=True) 
    weight_class = models.CharField(max_length=50, blank=True)
    age          = models.IntegerField(null=True, blank=True)
    best_squat   = models.IntegerField(default=0)
    best_bench   = models.IntegerField(default=0)
    best_dead    = models.IntegerField(default=0)
    total        = models.IntegerField(default=0)
    points       = models.FloatField(null=True, blank=True)

    def __str__(self):
        return self.athlete_name

    def set_total(self):
        """Recalculates and saves the athlete's total."""
        self.total = self.best_squat + self.best_bench + self.best_dead

    def calc_gl_points(self):
        """
        Calculates gl points based on bodyweight and total.
        """

        if not self.bw or not self.total:
            return

        if self.is_male:
            a, b, c = 1199.72839, -102.11299, 0.0000022
        else:
            a, b, c = 1249.1533, -123.9606, 0.0000062

        denominator = a + b * self.bw + c * self.bw ** 2
        if denominator == 0:
            return

        self.gl_points = (self.total / denominator) * 100