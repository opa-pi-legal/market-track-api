from django.db import models

from django.db import models

class Product(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]

    group_id = models.CharField(max_length=255)
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100, blank=True, null=True)
    category = models.CharField(max_length=80, default='Geral')
    barcode = models.CharField(max_length=64, blank=True, null=True)
    unit = models.CharField(max_length=20, default='un')
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1.0)
    photo_url = models.URLField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    added_by = models.CharField(max_length=128) 
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products"  

    def __str__(self):
        return f"{self.name} - {self.quantity} {self.unit}"