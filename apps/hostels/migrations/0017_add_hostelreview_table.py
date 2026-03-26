from django.db import migrations, models
import django.db.models.deletion
import uuid

class Migration(migrations.Migration):
    dependencies = [
        ('hostels', '0015_merge_20260312_1817'),  # Replace with your actual last applied migration
    ]

    operations = [
        migrations.CreateModel(
            name='HostelReview',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('rating', models.IntegerField(choices=[(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)])),
                ('comment', models.TextField()),
                ('is_approved', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('hostel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hostel_reviews', to='hostels.hostel')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.user')),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('hostel', 'user')},
            },
        ),
    ]