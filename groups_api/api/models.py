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

class UserInGroup(models.Model):
    group = models.ForeignKey(Groups, on_delete=models.CASCADE, related_name="members")
    user_id = models.CharField(max_length=128)
    is_admin = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "group_members"

    def __str__(self):
        admin_status = "Admin" "Membro" if self.is_admin else "Membro"
        return f"User {self.user_id} no Grupo {self.group.name} ({admin_status})"

class GroupInvite(models.Model):
    code = models.CharField(max_length=10, primary_key=True)
    group = models.ForeignKey('Groups', on_delete=models.CASCADE, related_name="invites")
    created_by = models.CharField(max_length=128)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "group_invites"  

    def __str__(self):
        status = "Ativo" if self.active else "Inativo"
        return f"Convite {self.code} para o grupo {self.group.name} ({status})"