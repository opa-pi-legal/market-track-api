from django.db import models

# Create your models here.
class User (models.Model):
    display_name = models.CharField( default="Usuário" ,max_length=255)
    email = models.EmailField( max_length=255)
    photo_url = models.URLField( null=True, blank=True)
    photo_public_id = models.CharField(max_length=255, null=True, blank=True)
    biometric_enabled = models.BooleanField(blank=True, null=True, default=False)
    last_active_group_id = models.CharField(max_length=255, null=True, blank=True)
    last_active_group_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField( auto_now=True)
    
    def __str__(self):
        return self.email

class UserInGroup (models.Model):
    group_id = models.CharField(max_length=255)
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, related_name="group_references")
    
    def __str__(self):
        return f"{self.user.email} no Grupo {self.group_id}"
    
class MarketId (models.Model):
    market_id = models.CharField(max_length=255)
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorite_markets")
    
    def __str__(self):
        return f"{self.market_id} para {self.user.email}"
    