from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('hostels', '0006_add_views_count_manual'),  # adjust to last migration
    ]

    operations = [
        migrations.AddField(
            model_name='hostelimage',
            name='description',
            field=models.CharField(blank=True, default='', max_length=255),
            preserve_default=False,
        ),
    ]