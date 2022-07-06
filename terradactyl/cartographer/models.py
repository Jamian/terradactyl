import datetime
import uuid

from django.db import models

from cartographer.utils.db import fields


from django.db import models
class TerraformCloudAPIKey(models.Model):
    name = models.CharField(max_length=128)
    value = fields.EncryptedCharField(max_length=128, null=True, blank=True)

class TerraformCloudOrganization(models.Model):
    name = models.CharField(max_length=128)
    api_key = models.ForeignKey(TerraformCloudAPIKey, on_delete=models.SET_NULL, null=True, blank=True)

    @property
    def refreshing(self):
        in_progress_sync_jobs = self.organizationsyncjob_set.filter(~models.Q(state=OrganizationSyncJob.COMPLETE))
        return True if in_progress_sync_jobs else False

class OrganizationSyncJob(models.Model):
    COMPLETE = 'COMPLETE'
    FETCHING_REMOTE_WORKSPACES = 'FETCHING_REMOTE_WORKSPACES'
    DRAWING_LOCAL_GRAPH = 'DRAWING_LOCAL_GRAPH'
    IMPORTING_STATE_HISTORY = 'IMPORTING_STATE_HISTORY'
    IMPORTING_RESOURCES = 'IMPORTING_RESOURCES'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    state = models.CharField(default=FETCHING_REMOTE_WORKSPACES, max_length=64, null=True, blank=True) # TODO : Make this an enum thing
    total_workspaces = models.IntegerField(default=0)
    organization = models.ForeignKey(TerraformCloudOrganization, on_delete=models.SET_NULL, null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    @property
    def in_progress(self):
        return self.state != OrganizationSyncJob.COMPLETE

    @property
    def duration(self):
        if self.finished_at:
            return self.finished_at - self.started_at
        else:
            return datetime.datetime.now().replace(tzinfo=None) - self.started_at.replace(tzinfo=None)
