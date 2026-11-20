from django.core.management.base import BaseCommand

from api.messaging import start_consumer
from api.models import Product


def handle_event(routing_key: str, payload: dict) -> None:
    if routing_key == 'group.deleted':
        group_id = payload.get('group_id')
        if group_id is not None:
            Product.objects.filter(group_id=str(group_id)).delete()


class Command(BaseCommand):
    help = 'Consume RabbitMQ group events for product_api'

    def handle(self, *args, **options):
        start_consumer(
            queue_name='product_api.group_events',
            binding_keys=['group.deleted'],
            handler_fn=handle_event,
        )
