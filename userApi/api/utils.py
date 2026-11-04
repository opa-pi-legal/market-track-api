import json
import pika
import dotenv
import os

dotenv.load_dotenv()
def publicar_evento_entrar_grupo(dados):
    rabbit_username = os.getenv("RABBITMQ_DEFAULT_USER")
    rabbit_pass = os.getenv("RABBITMQ_DEFAULT_PASS")
           
    credentials = pika.PlainCredentials(username=rabbit_username,password=rabbit_pass)
   
    connection = pika.BlockingConnection(pika.ConnectionParameters(host = "localhost", credentials=credentials))
    channel = connection.channel()
    channel.exchange_declare(exchange="evento_grupo", exchange_type="fanout")
    channel.basic_publish(
        exchange="evento_grupo",
        routing_key='',
        body=json.dumps(dados)
    )
    
    connection.close()
