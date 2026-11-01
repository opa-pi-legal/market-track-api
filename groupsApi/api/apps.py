from django.apps import AppConfig
import os
import consul

class ApiConfig(AppConfig):
    name = 'api'
    
    def ready(self):
        
        if os.environ.get("RUN_MAIN") == 'false':
            return
        
        service_address = os.environ.get("SERVICE_IP", "172.17.0.1")
        service_port = int(os.environ.get("SERVICE_PORT",8001))
        consul_address = os.environ.get("CONSUL_IP",'127.0.0.1')
        consul_port = int(os.environ.get("CONSUL_PORT",8500))
        
        try:
            c = consul.Consul(host=consul_address, port=consul_port)
            
            service_name = "groups-api"
            service_id = f"{service_name} - {os.environ.get("HOSTNAME","local")}"

            c.agent.service.register(
                name = service_name,
                service_id = service_id,
                address = service_address,
                port = service_port,
                check = {
                    "http" : f"http://{service_address}:{service_port}/health/",
                    "interval" : "10s",
                    "deregister_critical_service_after" : "1m"
                }
            )
            
            print("SUCCESS: Registered with Consul!")
        
        except Exception as e:
            print(f"ERROR: Could not register with Consul: {e}")