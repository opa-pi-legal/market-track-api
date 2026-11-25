from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_communityoffer_abuse_reports_count_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='communityoffer',
            name='market_address',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='communityoffer',
            name='market_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
    ]
