import math
import re
import unicodedata

# Lista enxuta de termos explícitos/impróprios para bloqueio síncrono (PT-BR).
# Validada por fronteira de palavra após normalização para evitar falsos positivos
# com alimentos comuns (ex.: cacau, peito de frango, linguiça, picolé, coco, alho).
BLOCKED_TERMS = {
    'piroca',
    'pinto',
    'penis',
    'pauzao',
    'rola',
    'caralho',
    'krl',
    'buceta',
    'xoxota',
    'xereca',
    'vagina',
    'cuzao',
    'boquete',
    'punheta',
    'porra',
    'putaria',
    'puta',
    'prostituta',
    'foder',
    'foda',
    'fodase',
    'arrombado',
    'viado',
    'bicha',
    'desgraca',
    'merda',
    'bosta',
    'corno',
    'porn',
    'porno',
    'sexo',
    'nude',
    'nudes',
    'dildo',
    'vibrador',
}

LEET_MAP = str.maketrans({
    '0': 'o',
    '1': 'i',
    '3': 'e',
    '4': 'a',
    '5': 's',
    '7': 't',
    '@': 'a',
    '$': 's',
    '!': 'i',
})

MIN_PRICE_CENTS = 25          # R$ 0,25
MAX_PRICE_CENTS = 500_000     # R$ 5.000,00
DAILY_OFFER_LIMIT = 15


def normalize_text(text: str) -> str:
    if not text:
        return ''
    decomposed = unicodedata.normalize('NFKD', text)
    ascii_only = ''.join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = ascii_only.lower().translate(LEET_MAP)
    collapsed = re.sub(r'(.)\1{2,}', r'\1', lowered)
    return re.sub(r'[^a-z0-9\s]+', ' ', collapsed).strip()


def contains_inappropriate_content(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    tokens = normalized.split()
    for token in tokens:
        if token in BLOCKED_TERMS:
            return True
    # Também checa termos compostos sem espaços (ex.: "p i r o c a")
    if len(tokens) >= 4 and all(len(t) == 1 for t in tokens):
        joined = ''.join(tokens)
        if joined in BLOCKED_TERMS:
            return True
    return False


def validate_price_cents(price_cents: int) -> tuple[bool, str | None]:
    if price_cents is None:
        return False, 'Informe um preço válido.'
    if price_cents < MIN_PRICE_CENTS:
        return False, 'Preço abaixo do mínimo permitido (R$ 0,25).'
    if price_cents > MAX_PRICE_CENTS:
        return False, 'Preço acima do máximo permitido (R$ 5.000,00).'
    return True, None


def is_valid_ean(code: str) -> bool:
    digits = re.sub(r'\D', '', code or '')
    if len(digits) not in (8, 12, 13, 14):
        return False
    nums = [int(d) for d in digits]
    check = nums[-1]
    body = nums[:-1]
    total = 0
    for idx, digit in enumerate(reversed(body)):
        total += digit * (3 if idx % 2 == 0 else 1)
    expected = (10 - (total % 10)) % 10
    return check == expected


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bounding_box(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    lat_delta = radius_km / 111.32
    cos_lat = max(0.01, math.cos(math.radians(lat)))
    lng_delta = radius_km / (111.32 * cos_lat)
    return (lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta)
