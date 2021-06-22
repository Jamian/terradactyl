from cartographer.utils.db import fields

from django.db import models
class TerraformCloudAPIKey(models.Model):
    name = models.CharField(max_length=128)
    value = fields.EncryptedCharField(max_length=128, null=True, blank=True)

class TerraformCloudOrganization(models.Model):
    name = models.CharField(max_length=128)
    api_key = models.ForeignKey(TerraformCloudAPIKey, on_delete=models.SET_NULL, null=True, blank=True)
    refreshing = models.BooleanField(default=False)
