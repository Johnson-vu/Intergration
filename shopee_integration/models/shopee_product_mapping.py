import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .. import const

_logger = logging.getLogger(__name__)


class ShopeeProductMapping(models.Model):
    _name = 'shopee.product.mapping'
    _description = 'Mapping Sản phẩm Odoo - Shopee'
    _rec_name = 'display_name'

    shopee_config_id = fields.Many2one(
        'shopee.config', string='Shop Shopee', required=True, ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product', string='Sản phẩm Odoo', required=True
    )
    product_tmpl_id = fields.Many2one(
        'product.template', string='Mẫu sản phẩm', related='product_id.product_tmpl_id'
    )
    shopee_item_id = fields.Char('Shopee Item ID')
    shopee_model_id = fields.Char('Shopee Model ID', help='ID biến thể sản phẩm trên Shopee')
    shopee_item_sku = fields.Char('Shopee SKU')
    shopee_price = fields.Float('Giá trên Shopee', digits=(16, 0))
    shopee_stock = fields.Integer('Tồn kho trên Shopee')
    last_sync_date = fields.Datetime('Lần đồng bộ cuối')
    sync_state = fields.Selection(
        selection=[
            (const.SYNC_STATE_SYNCED, 'Đã đồng bộ'),
            (const.SYNC_STATE_PENDING, 'Chờ đồng bộ'),
            (const.SYNC_STATE_ERROR, 'Lỗi'),
        ],
        default=const.SYNC_STATE_PENDING,
        string='Trạng thái',
    )
    sync_error_message = fields.Text('Lỗi đồng bộ')
    display_name = fields.Char(compute='_compute_display_name', store=True)

    _sql_constraints = [
        (
            'unique_product_config',
            'UNIQUE(product_id, shopee_config_id)',
            'Sản phẩm này đã được map với shop Shopee này rồi.',
        ),
    ]

    @api.depends('product_id', 'shopee_config_id')
    def _compute_display_name(self):
        for rec in self:
            product = rec.product_id.display_name or ''
            shop = rec.shopee_config_id.name or ''
            rec.display_name = f'{product} [{shop}]'

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_push_to_shopee(self):
        """Đẩy sản phẩm từ Odoo lên Shopee."""
        for rec in self:
            if rec.shopee_config_id.state != const.CONFIG_STATE_AUTHORIZED:
                raise UserError(_('Shop "%s" chưa kết nối với Shopee.') % rec.shopee_config_id.name)
            try:
                api = rec.shopee_config_id._get_api_client()
                item_data = rec._build_item_data()
                if rec.shopee_item_id:
                    item_data['item_id'] = int(rec.shopee_item_id)
                    result = api.update_item(item_data)
                else:
                    result = api.add_item(item_data)
                    rec.shopee_item_id = str(result.get('response', {}).get('item_id', ''))
                rec.write({
                    'sync_state': const.SYNC_STATE_SYNCED,
                    'last_sync_date': fields.Datetime.now(),
                    'sync_error_message': False,
                })
            except Exception as e:
                rec.write({
                    'sync_state': const.SYNC_STATE_ERROR,
                    'sync_error_message': str(e),
                })
                _logger.error('Push product to Shopee failed for %s: %s', rec.product_id.name, e)

    def action_pull_from_shopee(self):
        """Kéo thông tin sản phẩm từ Shopee về."""
        for rec in self:
            if not rec.shopee_item_id:
                raise UserError(_('Sản phẩm chưa có Shopee Item ID.'))
            try:
                api = rec.shopee_config_id._get_api_client()
                result = api.get_item_detail([int(rec.shopee_item_id)])
                items = result.get('response', {}).get('item_list', [])
                if items:
                    rec._update_from_shopee_data(items[0])
            except Exception as e:
                _logger.error('Pull product from Shopee failed: %s', e)
                raise UserError(_('Lỗi kéo sản phẩm: %s') % str(e))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_item_data(self):
        """Tạo dict dữ liệu sản phẩm để đẩy lên Shopee."""
        product = self.product_id
        tmpl = product.product_tmpl_id
        return {
            'original_price': self.shopee_price or tmpl.list_price,
            'description': tmpl.description_sale or tmpl.name,
            'item_name': tmpl.name,
            'normal_stock': self.shopee_stock or 0,
            'weight': tmpl.weight or 0.1,
            'item_sku': product.default_code or '',
            'logistics_info': [],
            'attribute_list': [],
            'image': {'image_id_list': []},
            'category_id': 0,
            'condition': 'NEW',
        }

    def _update_from_shopee_data(self, item_data):
        """Cập nhật thông tin từ Shopee response."""
        price_info = item_data.get('price_info', [{}])
        original_price = price_info[0].get('original_price', 0) if price_info else 0
        self.write({
            'shopee_item_sku': item_data.get('item_sku', ''),
            'shopee_price': original_price,
            'shopee_stock': item_data.get('stock_info_v2', {}).get('summary_info', {}).get('total_available_stock', 0),
            'sync_state': const.SYNC_STATE_SYNCED,
            'last_sync_date': fields.Datetime.now(),
        })

    def _sync_stock_for_config(self, config):
        """Đồng bộ tồn kho cho tất cả sản phẩm của một shop."""
        mappings = self.search([
            ('shopee_config_id', '=', config.id),
            ('shopee_item_id', '!=', False),
        ])
        if not mappings:
            return

        api = config._get_api_client()
        stock_list = []
        for m in mappings:
            qty = m.product_id.with_context(
                warehouse=config.warehouse_id.id
            ).qty_available
            entry = {
                'item_id': int(m.shopee_item_id),
                'stock_list': [{
                    'model_id': int(m.shopee_model_id) if m.shopee_model_id else 0,
                    'seller_stock': [{'stock': int(qty)}],
                }],
            }
            stock_list.append(entry)

        try:
            api.update_stock(stock_list)
            mappings.write({'shopee_stock': 0, 'last_sync_date': fields.Datetime.now()})
            _logger.info('Synced stock for %d products in shop %s', len(mappings), config.name)
        except Exception as e:
            _logger.error('Stock sync failed for shop %s: %s', config.name, e)

    @api.model
    def _cron_sync_stock(self):
        """Cron: đồng bộ tồn kho cho tất cả shop đang active."""
        configs = self.env['shopee.config'].search([
            ('state', '=', const.CONFIG_STATE_AUTHORIZED)
        ])
        for config in configs:
            self._sync_stock_for_config(config)
