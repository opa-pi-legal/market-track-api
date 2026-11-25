from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_market_city_market_latitude_market_longitude'),
    ]

    operations = [
        migrations.AddField(
            model_name='market',
            name='is_verified',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='market',
            name='linked_group_ids',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='market',
            name='osm_place_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=128),
        ),
    ]
