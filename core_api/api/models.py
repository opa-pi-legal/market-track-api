from django.db import models

class User (models.Model):
    display_name = models.CharField( default="Usuário" ,max_length=255)
    email = models.EmailField( max_length=255)
    photo_url = models.URLField( null=True, blank=True)
    photo_public_id = models.CharField(max_length=255, null=True, blank=True)
    biometric_enabled = models.BooleanField(blank=True, default=False)
    last_active_group = models.ForeignKey('Groups', on_delete=models.SET_NULL, null=True, blank=True, related_name='active_users')
    last_active_group_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField( auto_now=True)
    
    def __str__(self):
        return self.email

class Groups (models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    color = models.CharField(max_length=6, blank=True, null=True)
    photoUrl = models.URLField(blank=True, null=True)
    suggestedCatalogEnabled = models.BooleanField(null=True, blank=True, default=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class UserInGroup(models.Model):
    group = models.ForeignKey(Groups, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_admin = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "group_members"
        constraints = [
            models.UniqueConstraint(fields=["group", "user"], name="uniq_user_in_group"),
        ]
    def __str__(self):
        admin_status = "Admin" if self.is_admin else "Membro"
        return f"User {self.user.display_name} no Grupo {self.group.name} ({admin_status})"

class GroupInvite(models.Model):
    code = models.CharField(max_length=10, primary_key=True)
    group = models.ForeignKey(Groups, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)  
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "group_invites" 

    def __str__(self):
        status = "Active" if self.active else "Inactive"
        return f"Invite {self.code} ({status})"

class PriceRecord(models.Model):
    group = models.ForeignKey(Groups, on_delete=models.CASCADE)
    product_id = models.CharField(max_length=255)
    market_id = models.CharField(max_length=255)
    price_cents = models.BigIntegerField()
    is_promotion = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "price_records"  

    def __str__(self):
        return f"Preço: {self.price_cents / 100:.2f} pelo Produto {self.product_id} no Mercado {self.market_id}"

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

    group = models.ForeignKey(Groups, on_delete=models.CASCADE, related_name="shopping_lists")
    name = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='shared')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="owned_shopping_lists")
    budget_cents = models.BigIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "shopping_lists"  # Forces Django to map to your exact SQL table name

    def __str__(self):
        return f"{self.name} ({self.scope}) - {self.status}"

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