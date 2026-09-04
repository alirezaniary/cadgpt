# T-0073's third step: every review has a project after 0007's backfill, so the column
# can now be required. Safe to run directly after 0007 in the same deploy, or separately
# against a database this backfill already ran on.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('review', '0007_backfill_general_projects'),
    ]

    operations = [
        migrations.AlterField(
            model_name='review',
            name='project',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reviews', to='project.project', verbose_name='project'),
        ),
    ]
