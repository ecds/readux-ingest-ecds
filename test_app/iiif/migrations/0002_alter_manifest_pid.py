# Generated by Django 3.2.23 on 2024-02-01 13:40

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('iiif', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='manifest',
            name='pid',
            field=models.CharField(default=uuid.uuid4, max_length=255),
        ),
    ]