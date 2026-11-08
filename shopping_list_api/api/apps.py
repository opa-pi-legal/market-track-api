import os
from django.apps import AppConfig
import consul

class MyAppConfig(AppConfig):
    name = 'api' 

    def ready(self):
        
        if os.environ.get('RUN_MAIN') == 'false':
            return
        
        service_address = os.environ.get("SERVICE_IP", "shopping-list-api")
        service_port = int(os.environ.get("SERVICE_PORT",8006))
        consul_address = os.environ.get("CONSUL_IP",'consul')
        consul_port = int(os.environ.get("CONSUL_PORT",8500))
        
        try:
            c = consul.Consul(host=consul_address, port=consul_port)
            
            service_name = 'shopping-list-api'
            service_id = f"{service_name}-{os.environ.get('HOSTNAME', 'local')}"
            
            c.agent.service.register(
                name=service_name,
                service_id=service_id,
                address=service_address,
                port=service_port,
                check={
                    'http': f'http://{service_address}:{service_port}/shopping-list-api/health/',
                    'interval': '10s',
                    'deregister_critical_service_after': '1m'
                }
            )
        except Exception as e:
            print(f"ERROR: Could not register with Consul: {e}")