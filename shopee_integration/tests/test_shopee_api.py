from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase

from ..services.shopee_api import ShopeeAPI
from .. import utils


class TestShopeeAPI(TransactionCase):
    """Unit tests cho ShopeeAPI client - không cần Odoo DB, mock tất cả HTTP calls."""

    def setUp(self):
        super().setUp()
        self.api = ShopeeAPI(
            partner_id='123456',
            partner_key='test_secret_key',
            shop_id='789012',
            access_token='test_token',
            sandbox=True,
        )

    def test_generate_signature(self):
        """HMAC-SHA256 signature phải là hex string 64 ký tự."""
        sig = utils.generate_signature('my_key', 'base_string')
        self.assertIsInstance(sig, str)
        self.assertEqual(len(sig), 64)

    def test_auth_base_string_format(self):
        """Auth base string phải có format: partner_id + api_path + timestamp."""
        result = utils.build_auth_base_string(123456, '/api/v2/auth/token/get', 1700000000)
        self.assertEqual(result, '123456/api/v2/auth/token/get1700000000')

    def test_shop_base_string_format(self):
        """Shop base string phải có format: partner_id + path + timestamp + token + shop_id."""
        result = utils.build_shop_base_string(123456, '/api/v2/order/get_order_list', 1700000000, 'mytoken', 789012)
        self.assertEqual(result, '123456/api/v2/order/get_order_list1700000000mytoken789012')

    def test_get_auth_url(self):
        """get_auth_url phải trả về URL chứa partner_id và redirect."""
        api = ShopeeAPI(partner_id='123456', partner_key='secret', sandbox=True)
        url = api.get_auth_url('https://myodoo.com/shopee/auth/callback')
        self.assertIn('partner_id=123456', url)
        self.assertIn('sign=', url)
        self.assertIn('timestamp=', url)

    @patch('shopee_integration.services.shopee_api.requests.get')
    def test_get_order_list_success(self, mock_get):
        """get_order_list phải parse response và trả về data đúng."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'error': '',
            'message': '',
            'response': {
                'order_list': [{'order_sn': 'SN001'}, {'order_sn': 'SN002'}],
                'more': False,
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.api.get_order_list(time_from=1700000000, time_to=1700003600)
        orders = result['response']['order_list']
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0]['order_sn'], 'SN001')

    @patch('shopee_integration.services.shopee_api.requests.get')
    def test_get_order_list_api_error_raises(self, mock_get):
        """Khi Shopee trả về error code, phải raise ValueError."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'error': 'error_auth',
            'message': 'Invalid access token',
            'response': {},
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with self.assertRaises(ValueError) as ctx:
            self.api.get_order_list(time_from=1700000000, time_to=1700003600)
        self.assertIn('error_auth', str(ctx.exception))

    @patch('shopee_integration.services.shopee_api.requests.post')
    def test_update_stock_sends_correct_payload(self, mock_post):
        """update_stock phải gửi đúng cấu trúc stock_list."""
        mock_response = MagicMock()
        mock_response.json.return_value = {'error': '', 'message': '', 'response': {}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        stock_list = [{'item_id': 111, 'stock_list': [{'model_id': 0, 'seller_stock': [{'stock': 5}]}]}]
        self.api.update_stock(stock_list)

        call_kwargs = mock_post.call_args
        sent_body = call_kwargs[1]['json']
        self.assertIn('stock_list', sent_body)
        self.assertEqual(sent_body['stock_list'][0]['item_id'], 111)

    @patch('shopee_integration.services.shopee_api.requests.post')
    def test_get_access_token(self, mock_post):
        """get_access_token phải gửi đúng body và trả về response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'error': '',
            'message': '',
            'access_token': 'new_access',
            'refresh_token': 'new_refresh',
            'expire_in': 86400,
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        api = ShopeeAPI(partner_id='123456', partner_key='secret', sandbox=True)
        result = api.get_access_token(code='auth_code_123', shop_id='789012')
        self.assertEqual(result['access_token'], 'new_access')

        sent_body = mock_post.call_args[1]['json']
        self.assertEqual(sent_body['code'], 'auth_code_123')
        self.assertEqual(sent_body['shop_id'], 789012)
