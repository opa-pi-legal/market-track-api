from django.db import models

class GroupInvite(models.Model):
    code = models.CharField(max_length=10, primary_key=True)
    group_id = models.CharField(max_length=255)
    created_by = models.CharField(max_length=128)  
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "group_invites" 

    def __str__(self):
        status = "Active" if self.active else "Inactive"
        return f"Invite {self.code} ({status})"