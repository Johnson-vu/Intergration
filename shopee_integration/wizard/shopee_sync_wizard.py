import logging
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .. import const, utils

_logger = logging.getLogger(__name__)


class ShopeeSyncWizard(models.TransientModel):
    _name = 'shopee.sync.wizard'
    _description = 'Đồng bộ thủ công Shopee'

    shopee_config_id = fields.Many2one(
        'shopee.config', string='Shop Shopee', required=True,
        domain=[('state', '=', 'authorized')],
    )
    sync_type = fields.Selection(
        selection=[
            ('orders', 'Kéo đơn hàng từ Shopee'),
            ('stock', 'Đồng bộ tồn kho lên Shopee'),
            ('products', 'Kéo sản phẩm từ Shopee'),
        ],
        string='Loại đồng bộ',
        required=True,
        default='orders',
    )
    date_from = fields.Datetime(
        'Từ ngày',
        default=lambda self: datetime.now() - timedelta(hours=24),
    )
    date_to = fields.Datetime('Đến ngày', default=fields.Datetime.now)
    result_message = fields.Text('Kết quả', readonly=True)
    state = fields.Selection(
        [('draft', 'Chưa chạy'), ('done', 'Hoàn thành'), ('error', 'Lỗi')],
        default='draft',
    )

    def action_sync(self):
        self.ensure_one()
        config = self.shopee_config_id
        if config.state != const.CONFIG_STATE_AUTHORIZED:
            raise UserError(_('Shop "%s" chưa kết nối với Shopee.') % config.name)

        try:
            if self.sync_type == 'orders':
                self._sync_orders(config)
            elif self.sync_type == 'stock':
                self._sync_stock(config)
            elif self.sync_type == 'products':
                self._sync_products(config)
            self.state = 'done'
        except Exception as e:
            self.state = 'error'
            self.result_message = str(e)
            raise UserError(_('Đồng bộ thất bại: %s') % str(e))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'shopee.sync.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def _sync_orders(self, config):
        """Kéo đơn hàng theo khoảng thời gian được chọn."""
        api = config._get_api_client()
        time_from = int(self.date_from.timestamp()) if self.date_from else utils.get_timestamp() - 86400
        time_to = int(self.date_to.timestamp()) if self.date_to else utils.get_timestamp()

        cursor = ''
        more = True
        order_sns = []
        while more:
            result = api.get_order_list(
                time_from=time_from,
                time_to=time_to,
                cursor=cursor,
                page_size=const.ORDER_BATCH_SIZE,
            )
            response = result.get('response', {})
            order_list = response.get('order_list', [])
            order_sns.extend([o['order_sn'] for o in order_list])
            more = response.get('more', False)
            cursor = response.get('next_cursor', '')

        existing = self.env['shopee.order'].search([
            ('shopee_order_sn', 'in', order_sns),
            ('shopee_config_id', '=', config.id),
        ]).mapped('shopee_order_sn')
        new_sns = [sn for sn in order_sns if sn not in existing]

        created = 0
        for i in range(0, len(new_sns), const.ORDER_BATCH_SIZE):
            batch = new_sns[i:i + const.ORDER_BATCH_SIZE]
            detail_result = api.get_order_detail(batch)
            for order_data in detail_result.get('response', {}).get('order_list', []):
                try:
                    self.env['shopee.order']._create_from_shopee_data(order_data, config)
                    created += 1
                except Exception as e:
                    _logger.error('Sync order %s failed: %s', order_data.get('order_sn'), e)

        self.result_message = _(
            'Tìm thấy %(total)d đơn. Tạo mới %(created)d đơn.'
        ) % {'total': len(order_sns), 'created': created}

    def _sync_stock(self, config):
        """Đẩy tồn kho hiện tại lên Shopee."""
        self.env['shopee.product.mapping']._sync_stock_for_config(config)
        count = self.env['shopee.product.mapping'].search_count([
            ('shopee_config_id', '=', config.id),
            ('shopee_item_id', '!=', False),
        ])
        self.result_message = _('Đã đồng bộ tồn kho cho %(count)d sản phẩm.') % {'count': count}

    def _sync_products(self, config):
        """Kéo danh sách sản phẩm từ Shopee (tạo mapping nếu chưa có)."""
        api = config._get_api_client()
        offset = 0
        total_items = 0
        while True:
            result = api.get_item_list(offset=offset, page_size=const.ITEM_BATCH_SIZE)
            response = result.get('response', {})
            items = response.get('item', [])
            if not items:
                break
            total_items += len(items)
            item_ids = [i['item_id'] for i in items]
            detail_result = api.get_item_detail(item_ids)
            item_details = detail_result.get('response', {}).get('item_list', [])
            for item in item_details:
                item_id = str(item.get('item_id', ''))
                existing = self.env['shopee.product.mapping'].search([
                    ('shopee_item_id', '=', item_id),
                    ('shopee_config_id', '=', config.id),
                ], limit=1)
                if not existing:
                    # Tạo mapping chưa link product (cần link thủ công)
                    self.env['shopee.product.mapping'].create({
                        'shopee_config_id': config.id,
                        'shopee_item_id': item_id,
                        'shopee_item_sku': item.get('item_sku', ''),
                        'shopee_price': item.get('price_info', [{}])[0].get('original_price', 0),
                        'sync_state': const.SYNC_STATE_PENDING,
                        'product_id': False,
                    })
            if not response.get('has_next_page', False):
                break
            offset += len(items)

        self.result_message = _('Đã kéo %(count)d sản phẩm từ Shopee.') % {'count': total_items}
