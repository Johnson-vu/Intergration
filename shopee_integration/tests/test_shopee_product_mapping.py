from unittest.mock import patch, MagicMock

from odoo.exceptions import UserError

from .common import ShopeeCommon


class TestShopeeProductMapping(ShopeeCommon):

    @patch('shopee_integration.models.shopee_product_mapping.ShopeeAPI')
    def test_push_new_product_calls_add_item(self, _MockAPI):
        """Sản phẩm chưa có shopee_item_id → gọi add_item và lưu item_id."""
        mock_api = MagicMock()
        mock_api.add_item.return_value = {
            'error': '',
            'response': {'item_id': 999888777},
        }
        self.shopee_config._get_api_client = MagicMock(return_value=mock_api)

        new_mapping = self.env['shopee.product.mapping'].create({
            'shopee_config_id': self.shopee_config.id,
            'product_id': self.product.id,
            'shopee_price': 100000,
        })
        new_mapping.action_push_to_shopee()

        mock_api.add_item.assert_called_once()
        self.assertEqual(new_mapping.shopee_item_id, '999888777')
        self.assertEqual(new_mapping.sync_state, 'synced')

    @patch('shopee_integration.models.shopee_product_mapping.ShopeeAPI')
    def test_push_existing_product_calls_update_item(self, _MockAPI):
        """Sản phẩm đã có shopee_item_id → gọi update_item."""
        mock_api = MagicMock()
        mock_api.update_item.return_value = {'error': '', 'response': {}}
        self.shopee_config._get_api_client = MagicMock(return_value=mock_api)

        self.product_mapping.action_push_to_shopee()

        mock_api.update_item.assert_called_once()
        mock_api.add_item.assert_not_called()
        self.assertEqual(self.product_mapping.sync_state, 'synced')

    @patch('shopee_integration.models.shopee_product_mapping.ShopeeAPI')
    def test_push_product_api_error_sets_error_state(self, _MockAPI):
        """Khi API lỗi, sync_state phải là 'error' và lưu message."""
        mock_api = MagicMock()
        mock_api.update_item.side_effect = ValueError('Token expired')
        self.shopee_config._get_api_client = MagicMock(return_value=mock_api)

        self.product_mapping.action_push_to_shopee()
        self.assertEqual(self.product_mapping.sync_state, 'error')
        self.assertIn('Token expired', self.product_mapping.sync_error_message)

    @patch('shopee_integration.models.shopee_product_mapping.ShopeeAPI')
    def test_pull_from_shopee_updates_price_and_stock(self, _MockAPI):
        """pull_from_shopee phải cập nhật shopee_price và shopee_stock."""
        mock_api = MagicMock()
        mock_api.get_item_detail.return_value = {
            'error': '',
            'response': {
                'item_list': [{
                    'item_id': 111222333,
                    'item_sku': 'TEST-SKU-001',
                    'price_info': [{'original_price': 180000}],
                    'stock_info_v2': {
                        'summary_info': {'total_available_stock': 25}
                    },
                }]
            }
        }
        self.shopee_config._get_api_client = MagicMock(return_value=mock_api)

        self.product_mapping.action_pull_from_shopee()
        self.assertEqual(self.product_mapping.shopee_price, 180000)
        self.assertEqual(self.product_mapping.shopee_stock, 25)
        self.assertEqual(self.product_mapping.sync_state, 'synced')

    def test_pull_without_item_id_raises(self):
        """Không có shopee_item_id thì raise UserError."""
        mapping = self.env['shopee.product.mapping'].create({
            'shopee_config_id': self.shopee_config.id,
            'product_id': self.product.id,
        })
        with self.assertRaises(UserError):
            mapping.action_pull_from_shopee()

    @patch('shopee_integration.models.shopee_product_mapping.ShopeeAPI')
    def test_cron_sync_stock(self, _MockAPI):
        """Cron sync stock phải gọi update_stock với qty từ Odoo."""
        mock_api = MagicMock()
        mock_api.update_stock.return_value = {'error': '', 'response': {}}
        self.shopee_config._get_api_client = MagicMock(return_value=mock_api)

        self.env['shopee.product.mapping']._cron_sync_stock()
        mock_api.update_stock.assert_called_once()

        call_args = mock_api.update_stock.call_args[0][0]
        self.assertEqual(call_args[0]['item_id'], 111222333)
