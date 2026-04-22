import hashlib
import hmac
import json
from unittest.mock import patch, MagicMock

from odoo.tests.common import HttpCase

from .. import utils
from .common import FAKE_PARTNER_ID, FAKE_PARTNER_KEY, FAKE_SHOP_ID


class TestShopeeWebhook(HttpCase):
    """HTTP tests cho Shopee webhook controller."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')
        cls.shopee_config = cls.env['shopee.config'].create({
            'name': 'Webhook Test Shop',
            'partner_id_shopee': FAKE_PARTNER_ID,
            'partner_key': FAKE_PARTNER_KEY,
            'shop_id': FAKE_SHOP_ID,
            'access_token': 'test_token',
            'refresh_token': 'test_refresh',
            'state': 'authorized',
            'warehouse_id': cls.warehouse.id,
            'sandbox': True,
        })

    def _make_signature(self, path, timestamp, shop_id, body_str):
        base = f'{FAKE_PARTNER_ID}{path}{timestamp}{shop_id}{body_str}'
        return hmac.new(
            FAKE_PARTNER_KEY.encode('utf-8'),
            base.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()

    def test_webhook_valid_signature_returns_200(self):
        """Webhook với chữ ký đúng phải trả về 200 OK."""
        timestamp = utils.get_timestamp()
        payload = {
            'code': 3,
            'shop_id': int(FAKE_SHOP_ID),
            'timestamp': timestamp,
            'ordersn': 'SN_WH_001',
            'status': 'SHIPPED',
        }
        body_str = json.dumps(payload, separators=(',', ':'))
        sign = self._make_signature('/shopee/webhook', timestamp, FAKE_SHOP_ID, body_str)

        resp = self.url_open(
            '/shopee/webhook',
            data=body_str.encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': sign,
            },
        )
        self.assertEqual(resp.status_code, 200)

    def test_webhook_invalid_signature_returns_401(self):
        """Webhook với chữ ký sai phải trả về 401."""
        payload = json.dumps({
            'code': 3,
            'shop_id': int(FAKE_SHOP_ID),
            'timestamp': utils.get_timestamp(),
        })
        resp = self.url_open(
            '/shopee/webhook',
            data=payload.encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'wrong_signature',
            },
        )
        self.assertEqual(resp.status_code, 401)

    def test_webhook_deauth_sets_config_expired(self):
        """Event code=15 (deauth) phải set state='expired'."""
        timestamp = utils.get_timestamp()
        payload = {
            'code': 15,
            'shop_id': int(FAKE_SHOP_ID),
            'timestamp': timestamp,
        }
        body_str = json.dumps(payload, separators=(',', ':'))
        sign = self._make_signature('/shopee/webhook', timestamp, FAKE_SHOP_ID, body_str)

        self.url_open(
            '/shopee/webhook',
            data=body_str.encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': sign,
            },
        )
        self.shopee_config.invalidate_recordset()
        self.assertEqual(self.shopee_config.state, 'expired')

    def test_webhook_invalid_json_returns_400(self):
        """Payload không phải JSON hợp lệ phải trả về 400."""
        resp = self.url_open(
            '/shopee/webhook',
            data=b'not valid json {{{',
            headers={'Content-Type': 'application/json', 'Authorization': 'any'},
        )
        self.assertEqual(resp.status_code, 400)
