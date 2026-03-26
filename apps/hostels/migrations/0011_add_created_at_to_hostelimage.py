from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('hostels', '0010_add_description_final'),  # use your last migration
    ]

    operations = [
        migrations.AddField(
            model_name='hostelimage',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
            # Use null=True temporarily if you have existing rows
        ),
    ]