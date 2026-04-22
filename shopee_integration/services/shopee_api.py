import logging
import requests

from .. import const, utils

_logger = logging.getLogger(__name__)


class ShopeeAPI:
    """Client for Shopee Open Platform API v2."""

    def __init__(self, partner_id, partner_key, shop_id=None, access_token=None, sandbox=False):
        self.partner_id = int(partner_id)
        self.partner_key = partner_key
        self.shop_id = int(shop_id) if shop_id else None
        self.access_token = access_token
        self.base_url = const.SANDBOX_URL if sandbox else const.BASE_URL

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_auth_sign(self, api_path, timestamp):
        base = utils.build_auth_base_string(self.partner_id, api_path, timestamp)
        return utils.generate_signature(self.partner_key, base)

    def _get_shop_sign(self, api_path, timestamp):
        base = utils.build_shop_base_string(
            self.partner_id, api_path, timestamp, self.access_token, self.shop_id
        )
        return utils.generate_signature(self.partner_key, base)

    def _common_params(self, api_path, timestamp, auth=True):
        sign = self._get_shop_sign(api_path, timestamp) if auth else self._get_auth_sign(api_path, timestamp)
        params = {
            'partner_id': self.partner_id,
            'timestamp': timestamp,
            'sign': sign,
        }
        if auth:
            params['shop_id'] = self.shop_id
            params['access_token'] = self.access_token
        return params

    def _get(self, api_path, extra_params=None, auth=True):
        timestamp = utils.get_timestamp()
        params = self._common_params(api_path, timestamp, auth=auth)
        if extra_params:
            params.update(extra_params)
        url = self.base_url + api_path
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            _logger.error('Shopee GET %s error: %s', api_path, e)
            raise
        if data.get('error'):
            _logger.error('Shopee API error [%s]: %s', data.get('error'), data.get('message'))
            raise ValueError(f"Shopee API error: {data.get('error')} - {data.get('message')}")
        return data

    def _post(self, api_path, body, auth=True):
        timestamp = utils.get_timestamp()
        params = self._common_params(api_path, timestamp, auth=auth)
        url = self.base_url + api_path
        try:
            resp = requests.post(url, params=params, json=body, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            _logger.error('Shopee POST %s error: %s', api_path, e)
            raise
        if data.get('error'):
            _logger.error('Shopee API error [%s]: %s', data.get('error'), data.get('message'))
            raise ValueError(f"Shopee API error: {data.get('error')} - {data.get('message')}")
        return data

    # ------------------------------------------------------------------
    # OAuth
    # ------------------------------------------------------------------

    def get_auth_url(self, redirect_url):
        """Build Shopee OAuth authorization URL."""
        timestamp = utils.get_timestamp()
        sign = self._get_auth_sign(const.AUTH_URL, timestamp)
        params = (
            f'partner_id={self.partner_id}'
            f'&timestamp={timestamp}'
            f'&sign={sign}'
            f'&redirect={requests.utils.quote(redirect_url, safe="")}'
        )
        return f'{self.base_url}{const.AUTH_URL}?{params}'

    def get_access_token(self, code, shop_id):
        """Exchange authorization code for access token."""
        body = {
            'code': code,
            'shop_id': int(shop_id),
            'partner_id': self.partner_id,
        }
        return self._post(const.TOKEN_URL, body, auth=False)

    def refresh_access_token(self, refresh_token, shop_id):
        """Refresh an expired access token."""
        body = {
            'refresh_token': refresh_token,
            'shop_id': int(shop_id),
            'partner_id': self.partner_id,
        }
        return self._post(const.REFRESH_TOKEN_URL, body, auth=False)

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def get_order_list(self, time_from, time_to, order_status=None, cursor='', page_size=50):
        params = {
            'time_range_field': 'create_time',
            'time_from': int(time_from),
            'time_to': int(time_to),
            'page_size': page_size,
            'cursor': cursor,
            'response_optional_fields': 'order_status',
        }
        if order_status:
            params['order_status'] = order_status
        return self._get(const.ORDER_LIST_URL, params)

    def get_order_detail(self, order_sn_list, response_optional_fields=None):
        fields = response_optional_fields or (
            'buyer_user_id,buyer_username,estimated_shipping_fee,'
            'recipient_address,actual_shipping_fee,goods_to_declare,'
            'note,note_update_time,pay_time,items_list,pay_channel_list,'
            'shipping_carrier,payment_method,total_amount,buyer_cancel_reason,'
            'cancel_by,cancel_reason,actual_shipping_fee_confirmed,'
            'buyer_cpf_id,fulfillment_flag,pickup_done_time,package_list,'
            'shipping_carrier,buyer_username,invoice_data,checkout_shipping_carrier'
        )
        params = {
            'order_sn_list': ','.join(order_sn_list),
            'response_optional_fields': fields,
        }
        return self._get(const.ORDER_DETAIL_URL, params)

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def get_item_list(self, offset=0, page_size=100, item_status='NORMAL'):
        params = {
            'offset': offset,
            'page_size': page_size,
            'item_status': item_status,
        }
        return self._get(const.ITEM_LIST_URL, params)

    def get_item_detail(self, item_id_list):
        params = {'item_id_list': ','.join(str(i) for i in item_id_list)}
        return self._get(const.ITEM_DETAIL_URL, params)

    def add_item(self, item_data):
        return self._post(const.ADD_ITEM_URL, item_data)

    def update_item(self, item_data):
        return self._post(const.UPDATE_ITEM_URL, item_data)

    def update_stock(self, stock_list):
        """
        stock_list: [{'item_id': int, 'stock_list': [{'model_id': int, 'seller_stock': [{'stock': int}]}]}]
        """
        body = {'stock_list': stock_list}
        return self._post(const.UPDATE_STOCK_URL, body)

    def update_price(self, price_list):
        """
        price_list: [{'item_id': int, 'price_list': [{'model_id': int, 'original_price': float}]}]
        """
        body = {'price_list': price_list}
        return self._post(const.UPDATE_PRICE_URL, body)
