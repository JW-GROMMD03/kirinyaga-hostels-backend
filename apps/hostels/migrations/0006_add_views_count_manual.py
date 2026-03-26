from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('hostels', '0005_alter_amenity_options_alter_hostelamenity_options_and_more'),  # Use your actual last migration
    ]

    operations = [
        migrations.AddField(
            model_name='hostel',
            name='views_count',
            field=models.IntegerField(default=0, help_text='Number of times the hostel has been viewed'),
        ),
    ]