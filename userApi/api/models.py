from django.db import models

# Create your models here.
class User (models.Model):
    displayName = models.CharField( default="Usuário" ,max_length=255)
    email = models.EmailField( max_length=255)
    photoUrl = models.URLField( null=True, blank=True)
    photoPublicId = models.CharField( null=True, blank=True)
    biometricEnabled = models.BooleanField(blank=True, null=True, default=False)
    lastActiveGroupId = models.CharField(null=True, blank=True)
    lastActiveGroupUpdatedAt = models.DateTimeField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField( auto_now=True)

class GroupsIds (models.Model):
    groupid = models.CharField(name= "GroupId")
    userId = models.ForeignKey(User, on_delete=models.CASCADE, related_name="group_references")
    
class MarketIds (models.Model):
    marketIds = models.CharField(name="MarketIds")
    userId = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorite_markets")
    
    