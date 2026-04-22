from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from odoo.exceptions import UserError, ValidationError

from .common import ShopeeCommon, FAKE_PARTNER_ID, FAKE_PARTNER_KEY, FAKE_SHOP_ID


class TestShopeeConfig(ShopeeCommon):

    def test_create_config(self):
        """Tạo config thành công với đủ thông tin."""
        self.assertEqual(self.shopee_config.name, 'Test Shop VN')
        self.assertEqual(self.shopee_config.state, 'authorized')

    def test_duplicate_shop_id_raises(self):
        """Không được tạo 2 config với cùng shop_id."""
        with self.assertRaises(ValidationError):
            self.env['shopee.config'].create({
                'name': 'Duplicate Shop',
                'partner_id_shopee': FAKE_PARTNER_ID,
                'partner_key': FAKE_PARTNER_KEY,
                'shop_id': FAKE_SHOP_ID,
                'state': 'authorized',
                'warehouse_id': self.warehouse.id,
            })

    @patch('shopee_integration.models.shopee_config.ShopeeAPI')
    def test_action_test_connection_success(self, MockAPI):
        """Kết nối thành công trả về notification action."""
        mock_api_instance = MagicMock()
        mock_api_instance.get_order_list.return_value = {
            'error': '', 'response': {'order_list': []}
        }
        MockAPI.return_value = mock_api_instance

        result = self.shopee_config.action_test_connection()
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')
        self.assertEqual(result['params']['type'], 'success')

    @patch('shopee_integration.models.shopee_config.ShopeeAPI')
    def test_action_test_connection_fails_raises_user_error(self, MockAPI):
        """Kết nối lỗi phải raise UserError."""
        mock_api_instance = MagicMock()
        mock_api_instance.get_order_list.side_effect = ValueError('Invalid token')
        MockAPI.return_value = mock_api_instance

        with self.assertRaises(UserError):
            self.shopee_config.action_test_connection()

    def test_action_test_connection_draft_raises(self):
        """Không thể test kết nối khi chưa authorize."""
        draft_config = self.env['shopee.config'].create({
            'name': 'Draft Shop',
            'partner_id_shopee': '999',
            'partner_key': 'key',
            'state': 'draft',
            'warehouse_id': self.warehouse.id,
        })
        with self.assertRaises(UserError):
            draft_config.action_test_connection()

    @patch('shopee_integration.models.shopee_config.ShopeeAPI')
    def test_action_refresh_token(self, MockAPI):
        """Refresh token phải cập nhật access_token và state."""
        mock_api_instance = MagicMock()
        mock_api_instance.refresh_access_token.return_value = {
            'access_token': 'new_token_xyz',
            'refresh_token': 'new_refresh_xyz',
            'expire_in': 86400,
        }
        MockAPI.return_value = mock_api_instance

        self.shopee_config.action_refresh_token()
        self.assertEqual(self.shopee_config.access_token, 'new_token_xyz')
        self.assertEqual(self.shopee_config.state, 'authorized')

    def test_refresh_token_without_refresh_token_raises(self):
        """Không có refresh_token thì raise UserError."""
        self.shopee_config.refresh_token = False
        with self.assertRaises(UserError):
            self.shopee_config.action_refresh_token()

    @patch('shopee_integration.models.shopee_config.ShopeeAPI')
    def test_cron_refresh_tokens_only_authorized(self, MockAPI):
        """Cron chỉ làm mới token cho config state=authorized và gần hết hạn."""
        mock_api_instance = MagicMock()
        mock_api_instance.refresh_access_token.return_value = {
            'access_token': 'refreshed', 'refresh_token': 'refreshed_r', 'expire_in': 86400
        }
        MockAPI.return_value = mock_api_instance

        # Đặt token sắp hết hạn
        self.shopee_config.token_expire_time = datetime.utcnow() + timedelta(minutes=30)
        self.env['shopee.config']._cron_refresh_all_tokens()
        self.assertEqual(self.shopee_config.access_token, 'refreshed')

    def test_cron_skips_draft_config(self):
        """Cron không xử lý config ở state draft."""
        draft_config = self.env['shopee.config'].create({
            'name': 'Draft Config',
            'partner_id_shopee': '111',
            'partner_key': 'key',
            'state': 'draft',
            'warehouse_id': self.warehouse.id,
        })
        # Không raise exception, draft config bị bỏ qua
        self.env['shopee.config']._cron_refresh_all_tokens()
        self.assertEqual(draft_config.state, 'draft')
