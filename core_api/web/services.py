import os
import requests
from rest_framework_simplejwt.tokens import RefreshToken

MARKET_API_URL = os.environ.get('MARKET_API_INTERNAL_URL', 'http://market-api:8002/market-api/api')
PRODUCT_API_URL = os.environ.get('PRODUCT_API_INTERNAL_URL', 'http://product-api:8004/product-api/api')


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
            f'{MARKET_API_URL}/markets/',
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


def create_market(user, payload: dict) -> tuple[bool, str | None]:
    try:
        resp = requests.post(
            f'{MARKET_API_URL}/markets/',
            json=payload,
            headers=_auth_headers(user),
            timeout=4,
        )
        if resp.status_code in (200, 201):
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
