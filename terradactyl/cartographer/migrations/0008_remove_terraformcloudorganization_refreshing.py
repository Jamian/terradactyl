# Generated by Django 4.0.5 on 2022-07-05 12:38

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cartographer', '0007_organizationsyncjob_finished_at_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='terraformcloudorganization',
            name='refreshing',
        ),
    ]
