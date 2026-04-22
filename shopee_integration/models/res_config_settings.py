from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    shopee_auto_confirm_order = fields.Boolean(
        string='Tự động xác nhận đơn Shopee',
        config_parameter='shopee_integration.auto_confirm_order',
        help='Tự động xác nhận (confirm) sale order khi kéo đơn từ Shopee về.',
    )
    shopee_default_config_id = fields.Many2one(
        'shopee.config',
        string='Shop Shopee mặc định',
        config_parameter='shopee_integration.default_config_id',
    )
