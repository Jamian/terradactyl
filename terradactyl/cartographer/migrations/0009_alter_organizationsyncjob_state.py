# Generated by Django 4.0.5 on 2022-07-05 12:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cartographer', '0008_remove_terraformcloudorganization_refreshing'),
    ]

    operations = [
        migrations.AlterField(
            model_name='organizationsyncjob',
            name='state',
            field=models.CharField(blank=True, default='FETCHING_REMOTE_WORKSPACES', max_length=64, null=True),
        ),
    ]