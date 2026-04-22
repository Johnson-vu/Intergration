from odoo.tests.common import TransactionCase


FAKE_PARTNER_ID = '123456'
FAKE_PARTNER_KEY = 'test_partner_key_secret'
FAKE_SHOP_ID = '789012'
FAKE_ACCESS_TOKEN = 'test_access_token'
FAKE_REFRESH_TOKEN = 'test_refresh_token'


class ShopeeCommon(TransactionCase):
    """Base test class with shared fixtures for Shopee integration tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Warehouse
        cls.warehouse = cls.env.ref('stock.warehouse0')

        # Partner
        cls.partner = cls.env['res.partner'].create({
            'name': 'Shopee Test Customer',
            'customer_rank': 1,
        })

        # Product
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product Shopee',
            'type': 'product',
            'list_price': 150000,
            'default_code': 'TEST-SKU-001',
        })

        # Shopee config (already authorized)
        cls.shopee_config = cls.env['shopee.config'].create({
            'name': 'Test Shop VN',
            'partner_id_shopee': FAKE_PARTNER_ID,
            'partner_key': FAKE_PARTNER_KEY,
            'shop_id': FAKE_SHOP_ID,
            'access_token': FAKE_ACCESS_TOKEN,
            'refresh_token': FAKE_REFRESH_TOKEN,
            'state': 'authorized',
            'warehouse_id': cls.warehouse.id,
            'sandbox': True,
        })

        # Product mapping
        cls.product_mapping = cls.env['shopee.product.mapping'].create({
            'shopee_config_id': cls.shopee_config.id,
            'product_id': cls.product.id,
            'shopee_item_id': '111222333',
            'shopee_model_id': '0',
            'shopee_price': 150000,
            'shopee_stock': 10,
            'sync_state': 'synced',
        })

    @classmethod
    def _make_order_api_response(cls, order_sn='SN20240101001', status='READY_TO_SHIP'):
        """Tạo mock Shopee order detail API response."""
        return {
            'error': '',
            'message': '',
            'response': {
                'order_list': [{
                    'order_sn': order_sn,
                    'order_status': status,
                    'buyer_user_id': 99001,
                    'buyer_username': 'buyer_test',
                    'create_time': 1704067200,
                    'update_time': 1704067200,
                    'pay_time': 1704067300,
                    'total_amount': 150000,
                    'actual_shipping_fee': 20000,
                    'estimated_shipping_fee': 20000,
                    'payment_method': 'COD',
                    'shipping_carrier': 'SPX Express',
                    'note': 'Giao giờ hành chính',
                    'recipient_address': {
                        'name': 'Nguyen Van A',
                        'phone': '0901234567',
                        'full_address': '123 Nguyen Trai',
                        'district': 'Thanh Xuan',
                        'city': 'Ha Noi',
                        'state': '',
                    },
                    'item_list': [{
                        'item_id': 111222333,
                        'model_id': 0,
                        'item_name': 'Test Product Shopee',
                        'item_sku': 'TEST-SKU-001',
                        'model_quantity_purchased': 2,
                        'model_original_price': 150000,
                        'model_discounted_price': 140000,
                    }],
                }]
            }
        }

    @classmethod
    def _make_order_list_response(cls, order_sns):
        """Tạo mock get_order_list API response."""
        return {
            'error': '',
            'message': '',
            'response': {
                'order_list': [{'order_sn': sn} for sn in order_sns],
                'more': False,
                'next_cursor': '',
            }
        }
