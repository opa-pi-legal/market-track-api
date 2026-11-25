from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(max_length=255, unique=True)
    photo_url = models.URLField(max_length=500, null=True, blank=True)
    photo_public_id = models.CharField(max_length=255, null=True, blank=True)
    biometric_enabled = models.BooleanField(blank=True, default=False)
    last_active_group = models.ForeignKey(
        'Groups',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='active_users',
    )
    last_active_group_updated_at = models.DateTimeField(null=True, blank=True)
    preferred_radius_km = models.PositiveIntegerField(default=30, null=True, blank=True)
    community_banned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.email


class Groups(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    color = models.CharField(max_length=20, blank=True, null=True, default='10B981')
    photoUrl = models.URLField(max_length=500, blank=True, null=True)
    suggestedCatalogEnabled = models.BooleanField(null=True, blank=True, default=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class UserInGroup(models.Model):
    group = models.ForeignKey(Groups, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='group_memberships')
    role = models.CharField(max_length=32, default='member')
    is_admin = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'group_members'
        unique_together = (('group', 'user'),)

    def __str__(self):
        admin_status = 'Admin' if self.is_admin else 'Membro'
        return f'User {self.user.username} no Grupo {self.group.name} ({admin_status})'


class GroupInvite(models.Model):
    code = models.CharField(max_length=32, primary_key=True)
    group = models.ForeignKey(Groups, on_delete=models.CASCADE, related_name='invites')
    created_by = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='created_invites',
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'group_invites'

    def __str__(self):
        status = 'Active' if self.active else 'Inactive'
        return f'Invite {self.code} ({status})'


class PriceRecord(models.Model):
    group = models.ForeignKey(Groups, on_delete=models.CASCADE, related_name='price_records')
    product_id = models.CharField(max_length=255)
    market_id = models.CharField(max_length=255)
    price_cents = models.BigIntegerField()
    is_promotion = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='price_records',
        null=True,
        blank=True,
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'price_records'

    def __str__(self):
        return f'Preço: {self.price_cents / 100:.2f} pelo Produto {self.product_id} no Mercado {self.market_id}'


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

    group = models.ForeignKey(Groups, on_delete=models.CASCADE, related_name='shopping_lists')
    name = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='shared')
    owner = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='shopping_lists',
        null=True,
        blank=True,
    )
    budget_cents = models.BigIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'shopping_lists'

    def __str__(self):
        return f'{self.name} ({self.scope}) - {self.status}'


class ShoppingListItem(models.Model):
    shopping_list = models.ForeignKey(
        'ShoppingList',
        on_delete=models.CASCADE,
        related_name='items',
        db_column='list_id',
    )
    product_id = models.CharField(max_length=64, blank=True, null=True)
    product_name = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1.0)
    unit = models.CharField(max_length=20, default='un', blank=True)
    checked = models.BooleanField(default=False)
    selected_market = models.CharField(max_length=64, blank=True, null=True)
    selected_price_cents = models.BigIntegerField(blank=True, null=True)
    paid_price_cents = models.BigIntegerField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    added_by = models.CharField(max_length=128, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shopping_list_items'

    def __str__(self):
        status = 'Checked' if self.checked else 'Pending'
        return f'{self.quantity} {self.unit} of {self.product_name} ({status})'


class CommunityOffer(models.Model):
    MODERATION_CHOICES = [
        ('approved', 'Approved'),
        ('flagged', 'Flagged'),
        ('removed', 'Removed'),
    ]

    ean = models.CharField(max_length=64, blank=True, default='', db_index=True)
    product_name = models.CharField(max_length=160)
    brand = models.CharField(max_length=128, blank=True, default='')
    category = models.CharField(max_length=64, default='Geral')
    market_name = models.CharField(max_length=128)
    market_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    market_address = models.CharField(max_length=255, blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    price_cents = models.PositiveIntegerField()
    reference_avg_cents = models.PositiveIntegerField(null=True, blank=True)
    discount_percent = models.IntegerField(default=0)
    is_promotion = models.BooleanField(default=True)
    confirmations_count = models.PositiveIntegerField(default=1)
    reports_count = models.PositiveIntegerField(default=0)
    abuse_reports_count = models.PositiveIntegerField(default=0)
    moderation_status = models.CharField(
        max_length=16,
        choices=MODERATION_CHOICES,
        default='approved',
    )
    is_active = models.BooleanField(default=True)
    reported_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reported_offers',
    )
    group = models.ForeignKey(
        'Groups',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='community_offers',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'community_offers'

    def __str__(self):
        return f'{self.product_name} - {self.price_cents / 100:.2f} @ {self.market_name}'


class OfferVote(models.Model):
    VOTE_CHOICES = [
        ('confirm', 'Confirm'),
        ('expired', 'Expired'),
        ('abuse', 'Abuse'),
    ]

    offer = models.ForeignKey(
        'CommunityOffer',
        on_delete=models.CASCADE,
        related_name='votes',
    )
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='offer_votes',
    )
    vote_type = models.CharField(max_length=16, choices=VOTE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'offer_votes'
        unique_together = (('offer', 'user'),)

    def __str__(self):
        return f'Vote {self.vote_type} on Offer {self.offer_id} by User {self.user_id}'


class PriceAlert(models.Model):
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='price_alerts',
    )
    group = models.ForeignKey(
        'Groups',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='price_alerts',
    )
    offer = models.ForeignKey(
        'CommunityOffer',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alerts',
    )
    ean = models.CharField(max_length=64, blank=True, default='')
    product_name = models.CharField(max_length=160)
    market_name = models.CharField(max_length=128, blank=True, default='')
    previous_price_cents = models.IntegerField(null=True, blank=True)
    new_price_cents = models.IntegerField()
    discount_percent = models.IntegerField(default=0)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'price_alerts'

    def __str__(self):
        return f'PriceAlert({self.product_name}: {self.new_price_cents})'


class ActivityLog(models.Model):
    group = models.ForeignKey(
        'Groups',
        on_delete=models.CASCADE,
        related_name='activity_logs',
    )
    user_id = models.CharField(max_length=64, blank=True, null=True)
    action = models.CharField(max_length=64)
    entity_type = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=64, blank=True, null=True)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'activity_logs'

    def __str__(self):
        return f'ActivityLog({self.action} on {self.entity_type} {self.entity_id})'

