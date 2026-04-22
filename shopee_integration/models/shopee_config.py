import logging
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .. import const, utils
from ..services.shopee_api import ShopeeAPI

_logger = logging.getLogger(__name__)


class ShopeeConfig(models.Model):
    _name = 'shopee.config'
    _description = 'Cấu hình Shop Shopee'
    _rec_name = 'name'

    name = fields.Char('Tên shop', required=True)
    partner_id_shopee = fields.Char(
        'Partner ID', required=True,
        help='Partner ID lấy từ Shopee Open Platform (https://open.shopee.com/)'
    )
    partner_key = fields.Char(
        'Partner Key', required=True, groups='shopee_integration.group_shopee_manager',
        help='Partner Key bí mật từ Shopee Open Platform'
    )
    shop_id = fields.Char('Shop ID', readonly=True)
    shop_name = fields.Char('Tên shop Shopee', readonly=True)
    access_token = fields.Char(
        'Access Token', readonly=True, groups='shopee_integration.group_shopee_manager'
    )
    refresh_token = fields.Char(
        'Refresh Token', readonly=True, groups='shopee_integration.group_shopee_manager'
    )
    token_expire_time = fields.Datetime('Token hết hạn', readonly=True)
    state = fields.Selection(
        selection=[
            (const.CONFIG_STATE_DRAFT, 'Chưa kết nối'),
            (const.CONFIG_STATE_AUTHORIZED, 'Đã kết nối'),
            (const.CONFIG_STATE_EXPIRED, 'Token hết hạn'),
        ],
        default=const.CONFIG_STATE_DRAFT,
        string='Trạng thái',
        readonly=True,
    )
    sandbox = fields.Boolean('Môi trường Sandbox', default=False)
    company_id = fields.Many2one(
        'res.company', string='Công ty',
        default=lambda self: self.env.company, required=True
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Kho hàng', required=True,
        domain="[('company_id', '=', company_id)]"
    )
    pricelist_id = fields.Many2one(
        'product.pricelist', string='Bảng giá',
        help='Bảng giá áp dụng cho đơn hàng từ Shopee'
    )
    team_id = fields.Many2one(
        'crm.team', string='Đội Sales',
        help='Đội sales phụ trách đơn hàng Shopee'
    )
    order_count = fields.Integer('Số đơn hàng', compute='_compute_order_count')
    mapping_count = fields.Integer('Sản phẩm đã map', compute='_compute_mapping_count')

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    def _compute_order_count(self):
        for rec in self:
            rec.order_count = self.env['shopee.order'].search_count(
                [('shopee_config_id', '=', rec.id)]
            )

    def _compute_mapping_count(self):
        for rec in self:
            rec.mapping_count = self.env['shopee.product.mapping'].search_count(
                [('shopee_config_id', '=', rec.id)]
            )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @api.constrains('partner_id_shopee', 'shop_id')
    def _check_unique_shop(self):
        for rec in self:
            if rec.shop_id:
                duplicate = self.search([
                    ('shop_id', '=', rec.shop_id),
                    ('id', '!=', rec.id),
                ])
                if duplicate:
                    raise ValidationError(_('Shop ID "%s" đã được cấu hình.') % rec.shop_id)

    # ------------------------------------------------------------------
    # API helper
    # ------------------------------------------------------------------

    def _get_api_client(self):
        self.ensure_one()
        return ShopeeAPI(
            partner_id=self.partner_id_shopee,
            partner_key=self.partner_key,
            shop_id=self.shop_id,
            access_token=self.access_token,
            sandbox=self.sandbox,
        )

    def _get_redirect_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f'{base_url}/shopee/auth/callback'

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_authorize(self):
        """Redirect sang Shopee OAuth để lấy authorization code."""
        self.ensure_one()
        api = ShopeeAPI(
            partner_id=self.partner_id_shopee,
            partner_key=self.partner_key,
            sandbox=self.sandbox,
        )
        auth_url = api.get_auth_url(self._get_redirect_url())
        return {
            'type': 'ir.actions.act_url',
            'url': auth_url,
            'target': 'self',
        }

    def action_refresh_token(self):
        """Làm mới access token bằng refresh token."""
        self.ensure_one()
        if not self.refresh_token:
            raise UserError(_('Không có refresh token. Vui lòng kết nối lại với Shopee.'))
        api = ShopeeAPI(
            partner_id=self.partner_id_shopee,
            partner_key=self.partner_key,
            sandbox=self.sandbox,
        )
        try:
            result = api.refresh_access_token(self.refresh_token, self.shop_id)
            self._update_tokens(result)
        except Exception as e:
            self.state = const.CONFIG_STATE_EXPIRED
            raise UserError(_('Lỗi làm mới token: %s') % str(e))

    def action_test_connection(self):
        """Kiểm tra kết nối API."""
        self.ensure_one()
        if self.state != const.CONFIG_STATE_AUTHORIZED:
            raise UserError(_('Shop chưa được kết nối. Vui lòng kết nối với Shopee trước.'))
        try:
            api = self._get_api_client()
            # Thử kéo 1 đơn hàng để test
            now = utils.get_timestamp()
            api.get_order_list(time_from=now - 3600, time_to=now, page_size=1)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Kết nối thành công'),
                    'message': _('Đã kết nối thành công với Shopee shop "%s".') % self.name,
                    'type': 'success',
                },
            }
        except Exception as e:
            raise UserError(_('Lỗi kết nối: %s') % str(e))

    def action_view_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Đơn hàng Shopee - %s') % self.name,
            'res_model': 'shopee.order',
            'view_mode': 'list,form',
            'domain': [('shopee_config_id', '=', self.id)],
            'context': {'default_shopee_config_id': self.id},
        }

    def action_view_mappings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sản phẩm Shopee - %s') % self.name,
            'res_model': 'shopee.product.mapping',
            'view_mode': 'list,form',
            'domain': [('shopee_config_id', '=', self.id)],
            'context': {'default_shopee_config_id': self.id},
        }

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _update_tokens(self, api_result):
        """Cập nhật access_token và refresh_token từ kết quả API."""
        self.write({
            'access_token': api_result.get('access_token'),
            'refresh_token': api_result.get('refresh_token'),
            'token_expire_time': datetime.utcnow() + timedelta(
                seconds=api_result.get('expire_in', 86400)
            ),
            'state': const.CONFIG_STATE_AUTHORIZED,
        })

    def _set_tokens_from_auth(self, code, shop_id):
        """Trao đổi authorization code lấy tokens."""
        api = ShopeeAPI(
            partner_id=self.partner_id_shopee,
            partner_key=self.partner_key,
            sandbox=self.sandbox,
        )
        result = api.get_access_token(code, shop_id)
        self.shop_id = str(shop_id)
        self._update_tokens(result)

    # ------------------------------------------------------------------
    # Cron jobs
    # ------------------------------------------------------------------

    @api.model
    def _cron_refresh_all_tokens(self):
        """Làm mới token cho tất cả shop đang active."""
        threshold = datetime.utcnow() + timedelta(seconds=const.TOKEN_REFRESH_BUFFER)
        configs = self.search([
            ('state', '=', const.CONFIG_STATE_AUTHORIZED),
            ('token_expire_time', '<=', threshold),
        ])
        for config in configs:
            try:
                config.action_refresh_token()
                _logger.info('Refreshed token for Shopee shop: %s', config.name)
            except Exception as e:
                _logger.error('Failed to refresh token for %s: %s', config.name, e)
