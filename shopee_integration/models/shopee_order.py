import logging
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .. import const, utils

_logger = logging.getLogger(__name__)


class ShopeeOrder(models.Model):
    _name = 'shopee.order'
    _description = 'Đơn hàng Shopee'
    _rec_name = 'shopee_order_sn'
    _order = 'create_time desc'

    shopee_config_id = fields.Many2one(
        'shopee.config', string='Shop Shopee', required=True, ondelete='restrict'
    )
    shopee_order_sn = fields.Char('Mã đơn Shopee', required=True, index=True)
    order_status = fields.Selection(
        selection=const.ORDER_STATUSES,
        string='Trạng thái Shopee',
    )
    sale_order_id = fields.Many2one(
        'sale.order', string='Đơn bán hàng Odoo', readonly=True
    )
    # Buyer info
    buyer_user_id = fields.Char('Buyer User ID')
    buyer_username = fields.Char('Tên tài khoản Shopee')
    partner_id = fields.Many2one('res.partner', string='Khách hàng')
    # Shipping
    recipient_name = fields.Char('Người nhận')
    recipient_phone = fields.Char('SĐT người nhận')
    shipping_address = fields.Text('Địa chỉ giao hàng')
    logistics_tracking_number = fields.Char('Mã vận đơn')
    shipping_carrier = fields.Char('Đơn vị vận chuyển')
    # Financials
    total_amount = fields.Float('Tổng tiền', digits=(16, 0))
    actual_shipping_fee = fields.Float('Phí vận chuyển thực tế', digits=(16, 0))
    estimated_shipping_fee = fields.Float('Phí vận chuyển ước tính', digits=(16, 0))
    payment_method = fields.Char('Phương thức thanh toán')
    # Timestamps
    create_time = fields.Datetime('Ngày tạo trên Shopee')
    update_time = fields.Datetime('Cập nhật lần cuối')
    pay_time = fields.Datetime('Ngày thanh toán')
    # Lines
    line_ids = fields.One2many('shopee.order.line', 'order_id', string='Chi tiết đơn')
    note = fields.Text('Ghi chú khách')

    _sql_constraints = [
        (
            'unique_order_sn_config',
            'UNIQUE(shopee_order_sn, shopee_config_id)',
            'Mã đơn hàng Shopee này đã tồn tại trong hệ thống.',
        ),
    ]

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_create_sale_order(self):
        """Tạo sale order Odoo từ đơn Shopee."""
        for rec in self:
            if rec.sale_order_id:
                raise UserError(_('Đơn hàng này đã được tạo trong Odoo (SO: %s).') % rec.sale_order_id.name)
            rec._create_sale_order()

    def action_view_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_('Chưa có đơn bán hàng Odoo tương ứng.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_partner(self):
        """Tìm hoặc tạo mới res.partner từ thông tin buyer."""
        self.ensure_one()
        Partner = self.env['res.partner']
        # Tìm theo tên tài khoản Shopee (lưu trong ref)
        partner = Partner.search([
            ('comment', '=like', f'%shopee:{self.buyer_username}%')
        ], limit=1)
        if not partner:
            partner = Partner.create({
                'name': self.recipient_name or self.buyer_username or 'Shopee Customer',
                'phone': self.recipient_phone,
                'street': self.shipping_address,
                'comment': f'shopee:{self.buyer_username}',
                'customer_rank': 1,
            })
        return partner

    def _create_sale_order(self):
        """Tạo sale.order từ shopee.order."""
        self.ensure_one()
        config = self.shopee_config_id

        partner = self._get_or_create_partner()

        order_vals = {
            'partner_id': partner.id,
            'warehouse_id': config.warehouse_id.id,
            'note': self.note or '',
            'origin': f'Shopee/{self.shopee_order_sn}',
            'client_order_ref': self.shopee_order_sn,
        }
        if config.pricelist_id:
            order_vals['pricelist_id'] = config.pricelist_id.id
        if config.team_id:
            order_vals['team_id'] = config.team_id.id

        order_lines = []
        for line in self.line_ids:
            if not line.product_id:
                _logger.warning(
                    'Shopee order %s: no product mapping for item_id=%s, skipping line.',
                    self.shopee_order_sn, line.shopee_item_id
                )
                continue
            order_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'price_unit': line.discounted_price or line.original_price,
                'name': line.item_name,
            }))

        if not order_lines:
            _logger.warning('Shopee order %s has no mappable lines, skipping SO creation.', self.shopee_order_sn)
            return

        order_vals['order_line'] = order_lines
        sale_order = self.env['sale.order'].create(order_vals)
        self.write({
            'sale_order_id': sale_order.id,
            'partner_id': partner.id,
        })
        _logger.info('Created SO %s for Shopee order %s', sale_order.name, self.shopee_order_sn)
        return sale_order

    def _process_order_event(self, event_data):
        """Xử lý webhook event cho đơn hàng."""
        order_sn = event_data.get('ordersn')
        status = event_data.get('status')
        if not order_sn:
            return
        order = self.search([('shopee_order_sn', '=', order_sn)], limit=1)
        if order:
            order.order_status = status
            if status == const.ORDER_STATUS_CANCELLED and order.sale_order_id:
                order.sale_order_id.action_cancel()

    # ------------------------------------------------------------------
    # Cron: pull orders
    # ------------------------------------------------------------------

    @api.model
    def _cron_pull_orders(self):
        """Kéo đơn hàng mới từ tất cả shop Shopee."""
        configs = self.env['shopee.config'].search([
            ('state', '=', const.CONFIG_STATE_AUTHORIZED)
        ])
        for config in configs:
            try:
                self._pull_orders_for_config(config)
            except Exception as e:
                _logger.error('Pull orders failed for shop %s: %s', config.name, e)

    def _pull_orders_for_config(self, config):
        """Kéo đơn hàng mới trong 15 phút vừa qua."""
        api = config._get_api_client()
        time_to = utils.get_timestamp()
        time_from = time_to - 900  # 15 phút

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

        if not order_sns:
            return

        # Lọc những đơn chưa có trong DB
        existing = self.search([
            ('shopee_order_sn', 'in', order_sns),
            ('shopee_config_id', '=', config.id),
        ]).mapped('shopee_order_sn')
        new_sns = [sn for sn in order_sns if sn not in existing]

        if not new_sns:
            return

        # Kéo chi tiết từng batch
        for i in range(0, len(new_sns), const.ORDER_BATCH_SIZE):
            batch = new_sns[i:i + const.ORDER_BATCH_SIZE]
            detail_result = api.get_order_detail(batch)
            orders_data = detail_result.get('response', {}).get('order_list', [])
            for order_data in orders_data:
                try:
                    self._create_from_shopee_data(order_data, config)
                except Exception as e:
                    _logger.error('Failed to create order %s: %s', order_data.get('order_sn'), e)

    def _create_from_shopee_data(self, data, config):
        """Tạo shopee.order từ dữ liệu API."""
        recipient = data.get('recipient_address', {})
        address_parts = [
            recipient.get('full_address', ''),
            recipient.get('district', ''),
            recipient.get('city', ''),
            recipient.get('state', ''),
        ]
        shipping_address = ', '.join(p for p in address_parts if p)

        order = self.create({
            'shopee_config_id': config.id,
            'shopee_order_sn': data['order_sn'],
            'order_status': data.get('order_status'),
            'buyer_user_id': str(data.get('buyer_user_id', '')),
            'buyer_username': data.get('buyer_username', ''),
            'recipient_name': recipient.get('name', ''),
            'recipient_phone': recipient.get('phone', ''),
            'shipping_address': shipping_address,
            'shipping_carrier': data.get('shipping_carrier', ''),
            'total_amount': data.get('total_amount', 0),
            'actual_shipping_fee': data.get('actual_shipping_fee', 0),
            'estimated_shipping_fee': data.get('estimated_shipping_fee', 0),
            'payment_method': data.get('payment_method', ''),
            'note': data.get('note', ''),
            'create_time': utils.shopee_ts_to_datetime(data.get('create_time')),
            'update_time': utils.shopee_ts_to_datetime(data.get('update_time')),
            'pay_time': utils.shopee_ts_to_datetime(data.get('pay_time')),
        })

        # Tạo order lines
        for item in data.get('item_list', []):
            mapping = self.env['shopee.product.mapping'].search([
                ('shopee_item_id', '=', str(item.get('item_id'))),
                ('shopee_config_id', '=', config.id),
            ], limit=1)
            self.env['shopee.order.line'].create({
                'order_id': order.id,
                'shopee_item_id': str(item.get('item_id', '')),
                'shopee_model_id': str(item.get('model_id', '')),
                'product_id': mapping.product_id.id if mapping else False,
                'item_name': item.get('item_name', ''),
                'item_sku': item.get('item_sku', ''),
                'quantity': item.get('model_quantity_purchased', 1),
                'original_price': item.get('model_original_price', 0),
                'discounted_price': item.get('model_discounted_price', 0),
            })

        # Tự động tạo SO
        order._create_sale_order()
        return order


class ShopeeOrderLine(models.Model):
    _name = 'shopee.order.line'
    _description = 'Chi tiết đơn hàng Shopee'

    order_id = fields.Many2one(
        'shopee.order', string='Đơn hàng', required=True, ondelete='cascade'
    )
    shopee_item_id = fields.Char('Shopee Item ID')
    shopee_model_id = fields.Char('Shopee Model ID')
    product_id = fields.Many2one('product.product', string='Sản phẩm Odoo')
    item_name = fields.Char('Tên sản phẩm')
    item_sku = fields.Char('SKU')
    quantity = fields.Integer('Số lượng', default=1)
    original_price = fields.Float('Giá gốc', digits=(16, 0))
    discounted_price = fields.Float('Giá sau giảm', digits=(16, 0))
