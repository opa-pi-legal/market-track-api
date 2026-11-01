from django.db import models

# Create your models here.
class Groups (models.Model):
    name = models.CharField(max_length=255)
    adminId = models.CharField()
    inviteCode = models.CharField()
    description = models.TextField(blank=True, null=True)
    color = models.CharField(max_length=6, blank=True, null=True)
    photoUrl = models.URLField(blank=True, null=True)
    suggestedCatalogEnabled = models.BooleanField(null=True, blank=True, default=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name