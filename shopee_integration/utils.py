import hashlib
import hmac
import time


def generate_signature(partner_key, base_string):
    """Generate HMAC-SHA256 signature for Shopee API requests."""
    return hmac.new(
        partner_key.encode('utf-8'),
        base_string.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def build_auth_base_string(partner_id, api_path, timestamp):
    """Base string for unauthenticated requests (token exchange, auth URL)."""
    return f'{partner_id}{api_path}{timestamp}'


def build_shop_base_string(partner_id, api_path, timestamp, access_token, shop_id):
    """Base string for authenticated shop-level requests."""
    return f'{partner_id}{api_path}{timestamp}{access_token}{shop_id}'


def get_timestamp():
    return int(time.time())


def shopee_ts_to_datetime(timestamp):
    """Convert Shopee Unix timestamp to Python datetime (UTC)."""
    from datetime import datetime, timezone
    if not timestamp:
        return False
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None)
