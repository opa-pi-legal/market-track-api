from django.db import models

class Market(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]

    group_id = models.CharField(max_length=128)
    name = models.CharField(max_length=150)
    brand = models.CharField(max_length=100, blank=True, default='')
    address = models.TextField(blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    osm_place_id = models.CharField(max_length=128, blank=True, default='', db_index=True)
    is_verified = models.BooleanField(default=False, db_index=True)
    linked_group_ids = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    added_by = models.CharField(max_length=128)  
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "markets"  

    def __str__(self):
        return f"{self.name} - {self.brand}" if self.brand else self.name



