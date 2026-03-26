from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('hostels', '0011_add_created_at_to_hostelimage'),  # use your actual last migration
    ]

    operations = [
        migrations.AddField(
            model_name='hostelamenity',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
    ]