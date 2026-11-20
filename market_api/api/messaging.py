import json
import logging
import os
import time

import pika

logger = logging.getLogger(__name__)

EXCHANGE_NAME = 'market_track.events'


def _get_connection_params() -> pika.ConnectionParameters:
    host = os.environ.get('RABBITMQ_HOST', 'rabbitmq')
    port = int(os.environ.get('RABBITMQ_PORT', '5672'))
    user = os.environ.get('RABBITMQ_USER', 'guest')
    password = os.environ.get('RABBITMQ_PASS', 'guest')
    credentials = pika.PlainCredentials(user, password)
    return pika.ConnectionParameters(
        host=host,
        port=port,
        credentials=credentials,
        socket_timeout=2,
        blocked_connection_timeout=2,
    )


def publish_event(routing_key: str, payload: dict) -> None:
    if os.environ.get('DISABLE_RABBITMQ') == '1':
        return

    connection = None
    try:
        connection = pika.BlockingConnection(_get_connection_params())
        channel = connection.channel()
        channel.exchange_declare(
            exchange=EXCHANGE_NAME,
            exchange_type='topic',
            durable=True,
        )
        body = json.dumps(payload, default=str)
        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=routing_key,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type='application/json',
            ),
        )
    except Exception as exc:
        logger.warning('Failed to publish RabbitMQ event %s: %s', routing_key, exc)
    finally:
        if connection is not None and connection.is_open:
            try:
                connection.close()
            except Exception:
                pass


def start_consumer(queue_name: str, binding_keys: list[str], handler_fn) -> None:
    while True:
        connection = None
        try:
            connection = pika.BlockingConnection(_get_connection_params())
            channel = connection.channel()
            channel.exchange_declare(
                exchange=EXCHANGE_NAME,
                exchange_type='topic',
                durable=True,
            )
            channel.queue_declare(queue=queue_name, durable=True)
            for key in binding_keys:
                channel.queue_bind(
                    exchange=EXCHANGE_NAME,
                    queue=queue_name,
                    routing_key=key,
                )
            channel.basic_qos(prefetch_count=1)

            def _on_message(ch, method, properties, body):
                try:
                    payload = json.loads(body.decode('utf-8'))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    logger.error('Invalid JSON in queue %s: %s', queue_name, exc)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    return

                try:
                    handler_fn(method.routing_key, payload)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as exc:
                    logger.exception(
                        'Error handling event %s in queue %s: %s',
                        method.routing_key,
                        queue_name,
                        exc,
                    )
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            channel.basic_consume(queue=queue_name, on_message_callback=_on_message)
            logger.info('Started RabbitMQ consumer on queue=%s bindings=%s', queue_name, binding_keys)
            channel.start_consuming()
        except KeyboardInterrupt:
            logger.info('RabbitMQ consumer interrupted, shutting down.')
            break
        except Exception as exc:
            logger.warning('RabbitMQ consumer connection error (%s). Reconnecting in 5s...', exc)
            time.sleep(5)
        finally:
            if connection is not None and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    pass
