from unittest.mock import patch, MagicMock

from .common import ShopeeCommon


class TestShopeeOrder(ShopeeCommon):

    @patch('shopee_integration.models.shopee_order.ShopeeAPI', autospec=False)
    def test_pull_orders_creates_shopee_order_and_sale_order(self, _MockAPI):
        """Kéo đơn từ Shopee phải tạo shopee.order và sale.order."""
        order_sn = 'SN20240101001'
        list_response = self._make_order_list_response([order_sn])
        detail_response = self._make_order_api_response(order_sn)

        mock_api = MagicMock()
        mock_api.get_order_list.return_value = list_response
        mock_api.get_order_detail.return_value = detail_response
        self.shopee_config._get_api_client = MagicMock(return_value=mock_api)

        self.env['shopee.order']._pull_orders_for_config(self.shopee_config)

        shopee_order = self.env['shopee.order'].search([
            ('shopee_order_sn', '=', order_sn),
            ('shopee_config_id', '=', self.shopee_config.id),
        ])
        self.assertEqual(len(shopee_order), 1)
        self.assertEqual(shopee_order.buyer_username, 'buyer_test')
        self.assertEqual(shopee_order.total_amount, 150000)

        # Sale order phải được tạo tự động
        self.assertTrue(shopee_order.sale_order_id)
        sale_order = shopee_order.sale_order_id
        self.assertEqual(sale_order.origin, f'Shopee/{order_sn}')
        self.assertEqual(len(sale_order.order_line), 1)
        self.assertEqual(sale_order.order_line[0].product_uom_qty, 2)

    @patch('shopee_integration.models.shopee_order.ShopeeAPI', autospec=False)
    def test_pull_orders_idempotent(self, _MockAPI):
        """Kéo đơn 2 lần không tạo duplicate."""
        order_sn = 'SN20240101002'
        list_response = self._make_order_list_response([order_sn])
        detail_response = self._make_order_api_response(order_sn)

        mock_api = MagicMock()
        mock_api.get_order_list.return_value = list_response
        mock_api.get_order_detail.return_value = detail_response
        self.shopee_config._get_api_client = MagicMock(return_value=mock_api)

        self.env['shopee.order']._pull_orders_for_config(self.shopee_config)
        self.env['shopee.order']._pull_orders_for_config(self.shopee_config)

        orders = self.env['shopee.order'].search([
            ('shopee_order_sn', '=', order_sn),
            ('shopee_config_id', '=', self.shopee_config.id),
        ])
        self.assertEqual(len(orders), 1)

    @patch('shopee_integration.models.shopee_order.ShopeeAPI', autospec=False)
    def test_order_without_mapping_skips_sale_order_line(self, _MockAPI):
        """Đơn có item không có mapping → bỏ qua line đó, không crash."""
        order_sn = 'SN20240101003'
        list_response = self._make_order_list_response([order_sn])

        detail_response = self._make_order_api_response(order_sn)
        # Thay item_id thành một item chưa có mapping
        detail_response['response']['order_list'][0]['item_list'][0]['item_id'] = 999999999

        mock_api = MagicMock()
        mock_api.get_order_list.return_value = list_response
        mock_api.get_order_detail.return_value = detail_response
        self.shopee_config._get_api_client = MagicMock(return_value=mock_api)

        # Không được raise exception
        self.env['shopee.order']._pull_orders_for_config(self.shopee_config)

        order = self.env['shopee.order'].search([('shopee_order_sn', '=', order_sn)])
        self.assertEqual(len(order), 1)
        # Sale order không tạo vì không có line nào có product mapping
        self.assertFalse(order.sale_order_id)

    def test_get_or_create_partner_creates_new(self):
        """Buyer chưa có partner → tạo mới res.partner."""
        order = self.env['shopee.order'].create({
            'shopee_config_id': self.shopee_config.id,
            'shopee_order_sn': 'SN_PARTNER_TEST',
            'buyer_username': 'unique_buyer_xyz',
            'recipient_name': 'New Buyer',
            'recipient_phone': '0909090909',
        })
        partner = order._get_or_create_partner()
        self.assertEqual(partner.name, 'New Buyer')
        self.assertIn('shopee:unique_buyer_xyz', partner.comment)

    def test_get_or_create_partner_finds_existing(self):
        """Buyer đã có partner → tái sử dụng, không tạo trùng."""
        existing_partner = self.env['res.partner'].create({
            'name': 'Existing Buyer',
            'comment': 'shopee:known_buyer',
        })
        order = self.env['shopee.order'].create({
            'shopee_config_id': self.shopee_config.id,
            'shopee_order_sn': 'SN_EXISTING_PARTNER',
            'buyer_username': 'known_buyer',
            'recipient_name': 'Existing Buyer',
        })
        partner = order._get_or_create_partner()
        self.assertEqual(partner.id, existing_partner.id)

    def test_process_order_event_updates_status(self):
        """Webhook event ORDER phải cập nhật order_status."""
        order = self.env['shopee.order'].create({
            'shopee_config_id': self.shopee_config.id,
            'shopee_order_sn': 'SN_WEBHOOK_001',
            'order_status': 'READY_TO_SHIP',
        })
        self.env['shopee.order']._process_order_event({
            'ordersn': 'SN_WEBHOOK_001',
            'status': 'SHIPPED',
        })
        self.assertEqual(order.order_status, 'SHIPPED')

    def test_process_cancelled_event_cancels_sale_order(self):
        """Khi Shopee hủy đơn → sale.order cũng bị hủy."""
        order = self.env['shopee.order'].create({
            'shopee_config_id': self.shopee_config.id,
            'shopee_order_sn': 'SN_CANCEL_001',
            'order_status': 'READY_TO_SHIP',
        })
        sale_order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'origin': 'Shopee/SN_CANCEL_001',
        })
        order.sale_order_id = sale_order.id

        self.env['shopee.order']._process_order_event({
            'ordersn': 'SN_CANCEL_001',
            'status': 'CANCELLED',
        })
        self.assertEqual(order.order_status, 'CANCELLED')
        self.assertEqual(sale_order.state, 'cancel')
