import os
import time
import requests
from django.db import connection
from rest_framework_simplejwt.tokens import RefreshToken

MARKET_API_URL = os.environ.get('MARKET_API_INTERNAL_URL', 'http://market-api:8002/market-api/api')
PRODUCT_API_URL = os.environ.get('PRODUCT_API_INTERNAL_URL', 'http://product-api:8004/product-api/api')
CONSUL_HOST = os.environ.get('CONSUL_IP', 'consul')
CONSUL_PORT = os.environ.get('CONSUL_PORT', '8500')
RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'rabbitmq')
RABBITMQ_MGMT_PORT = os.environ.get('RABBITMQ_MGMT_PORT', '15672')
RABBITMQ_USER = os.environ.get('RABBITMQ_USER', 'guest')
RABBITMQ_PASS = os.environ.get('RABBITMQ_PASS', 'guest')


def _auth_headers(user) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh['is_staff'] = bool(getattr(user, 'is_staff', False))
    return {
        'Authorization': f'Bearer {str(refresh.access_token)}',
        'Content-Type': 'application/json',
    }


def fetch_markets(user, group_id) -> list[dict]:
    if not group_id:
        return []
    try:
        resp = requests.get(
            f'{MARKET_API_URL}/market/',
            params={'group_id': str(group_id)},
            headers=_auth_headers(user),
            timeout=3,
        )
        if resp.ok:
            data = resp.json()
            return data if isinstance(data, list) else data.get('results', [])
    except Exception:
        pass
    return []


def fetch_all_markets(user) -> list[dict]:
    try:
        resp = requests.get(
            f'{MARKET_API_URL}/market/',
            params={'all_groups': 'true'},
            headers=_auth_headers(user),
            timeout=3,
        )
        if resp.ok:
            data = resp.json()
            return data if isinstance(data, list) else data.get('results', [])
    except Exception:
        pass
    return []


def create_market(user, payload: dict) -> tuple[bool, str | None]:
    try:
        resp = requests.post(
            f'{MARKET_API_URL}/market/',
            json=payload,
            headers=_auth_headers(user),
            timeout=4,
        )
        if resp.status_code in (200, 201):
            return True, None
        return False, resp.text[:200]
    except Exception as exc:
        return False, str(exc)


def update_market(user, market_id: int, payload: dict) -> tuple[bool, str | None]:
    try:
        resp = requests.patch(
            f'{MARKET_API_URL}/market/{market_id}/',
            json=payload,
            headers=_auth_headers(user),
            timeout=4,
        )
        if resp.ok:
            return True, None
        return False, resp.text[:200]
    except Exception as exc:
        return False, str(exc)


def fetch_products(user, group_id, include_global: bool = True, query: str = '') -> list[dict]:
    if not group_id:
        return []
    params = {
        'group_id': str(group_id),
        'include_global': 'true' if include_global else 'false',
    }
    if query:
        params['q'] = query
    try:
        resp = requests.get(
            f'{PRODUCT_API_URL}/products/',
            params=params,
            headers=_auth_headers(user),
            timeout=3,
        )
        if resp.ok:
            data = resp.json()
            return data if isinstance(data, list) else data.get('results', [])
    except Exception:
        pass
    return []


def fetch_all_products(user) -> list[dict]:
    try:
        resp = requests.get(
            f'{PRODUCT_API_URL}/products/',
            params={'all_groups': 'true'},
            headers=_auth_headers(user),
            timeout=3,
        )
        if resp.ok:
            data = resp.json()
            return data if isinstance(data, list) else data.get('results', [])
    except Exception:
        pass
    return []


def create_product(user, payload: dict) -> tuple[bool, str | None]:
    try:
        resp = requests.post(
            f'{PRODUCT_API_URL}/products/',
            json=payload,
            headers=_auth_headers(user),
            timeout=4,
        )
        if resp.status_code in (200, 201):
            return True, None
        return False, resp.text[:200]
    except Exception as exc:
        return False, str(exc)


def promote_product_global(user, product_id: int) -> tuple[bool, str | None]:
    try:
        resp = requests.post(
            f'{PRODUCT_API_URL}/products/{product_id}/promote-global/',
            json={'verified_source': 'admin'},
            headers=_auth_headers(user),
            timeout=4,
        )
        if resp.ok:
            return True, None
        return False, resp.text[:200]
    except Exception as exc:
        return False, str(exc)


def _probe_http(name: str, url: str) -> dict:
    start = time.monotonic()
    try:
        resp = requests.get(url, timeout=1.5)
        latency = int(round((time.monotonic() - start) * 1000))
        return {
            'name': name,
            'ok': resp.status_code == 200,
            'latency_ms': latency,
            'detail': f'HTTP {resp.status_code}',
            'endpoint': url,
        }
    except Exception:
        latency = int(round((time.monotonic() - start) * 1000))
        return {
            'name': name,
            'ok': False,
            'latency_ms': latency,
            'detail': 'Indisponível',
            'endpoint': url,
        }


def check_services_health() -> list[dict]:
    results = []

    # 1. core-api (serviço local atual)
    results.append({
        'name': 'core-api',
        'ok': True,
        'latency_ms': 1,
        'detail': 'HTTP 200',
        'endpoint': '/core-api/health/',
    })

    # 2. PostgreSQL (core_db)
    start = time.monotonic()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        db_ok = True
        db_detail = 'Conectado'
    except Exception:
        db_ok = False
        db_detail = 'Erro de conexão'
    results.append({
        'name': 'PostgreSQL',
        'ok': db_ok,
        'latency_ms': int(round((time.monotonic() - start) * 1000)),
        'detail': db_detail,
        'endpoint': 'SELECT 1 (core_db)',
    })

    # 3. market-api & product-api
    market_health = MARKET_API_URL.replace('/api', '/health/')
    product_health = PRODUCT_API_URL.replace('/api', '/health/')
    results.append(_probe_http('market-api', market_health))
    results.append(_probe_http('product-api', product_health))

    # 4. Consul
    consul_url = f'http://{CONSUL_HOST}:{CONSUL_PORT}/v1/health/state/any'
    start = time.monotonic()
    try:
        resp = requests.get(consul_url, timeout=1.5)
        latency = int(round((time.monotonic() - start) * 1000))
        if resp.ok:
            checks = resp.json() if isinstance(resp.json(), list) else []
            passing = sum(1 for c in checks if c.get('Status') == 'passing')
            results.append({
                'name': 'Consul',
                'ok': True,
                'latency_ms': latency,
                'detail': f'{passing}/{len(checks)} passing',
                'endpoint': consul_url,
            })
        else:
            results.append({
                'name': 'Consul',
                'ok': False,
                'latency_ms': latency,
                'detail': f'HTTP {resp.status_code}',
                'endpoint': consul_url,
            })
    except Exception:
        results.append({
            'name': 'Consul',
            'ok': False,
            'latency_ms': int(round((time.monotonic() - start) * 1000)),
            'detail': 'Indisponível',
            'endpoint': consul_url,
        })

    return results


def fetch_rabbitmq_queues() -> tuple[list[dict], bool]:
    url = f'http://{RABBITMQ_HOST}:{RABBITMQ_MGMT_PORT}/api/queues'
    try:
        resp = requests.get(url, auth=(RABBITMQ_USER, RABBITMQ_PASS), timeout=1.5)
        if resp.ok:
            raw = resp.json()
            queues = []
            for q in raw if isinstance(raw, list) else []:
                queues.append({
                    'name': q.get('name', '-'),
                    'consumers': q.get('consumers', 0),
                    'messages': q.get('messages', 0),
                    'messages_ready': q.get('messages_ready', 0),
                    'state': q.get('state', 'unknown'),
                })
            return queues, True
    except Exception:
        pass
    return [], False
