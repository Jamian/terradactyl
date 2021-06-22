# Generated by Django 3.1.7 on 2021-03-17 08:57

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Repository',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
                ('clone_href', models.CharField(blank=True, max_length=256, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='TerraformProject',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
                ('relative_path', models.TextField(blank=True, null=True)),
                ('repository', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='cartographer.repository')),
            ],
        ),
    ]
