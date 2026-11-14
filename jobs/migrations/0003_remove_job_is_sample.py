from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0002_jobapplication_savedjob_job_company_name_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='job',
            name='is_sample',
        ),
    ]
