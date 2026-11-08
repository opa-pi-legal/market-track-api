from django.db import models

class ShoppingList(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]

    SCOPE_CHOICES = [
        ('shared', 'Shared'),
        ('personal', 'Personal'),
    ]

    group = models.CharField(max_length=255)
    name = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='shared')
    owner_id = models.CharField(max_length=128)
    budget_cents = models.BigIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "shopping_lists"  # Forces Django to map to your exact SQL table name

    def __str__(self):
        return f"{self.name} ({self.scope}) - {self.status}"

import uuid
from django.db import models

class ShoppingListItem(models.Model):
    shopping_list = models.ForeignKey(
        'ShoppingList', 
        on_delete=models.CASCADE, 
        related_name="items", 
        db_column="list_id"
    )
    product_id = models.CharField(max_length=200, blank=True, null=True)  
    product_name = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1.0)
    unit = models.CharField(max_length=20, default='un')
    checked = models.BooleanField(default=False)
    selected_market = models.CharField(max_length=100, blank=True, null=True)
    selected_price_cents = models.BigIntegerField(blank=True, null=True)
    paid_price_cents = models.BigIntegerField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    added_by = models.CharField(max_length=128)  
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shopping_list_items"

    def __str__(self):
        status = "Checked" if self.checked else "Pending"
        return f"{self.quantity} {self.unit} of {self.product_name} ({status})"