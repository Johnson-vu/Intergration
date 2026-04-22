import hashlib
import hmac
import json
import logging

from odoo import http
from odoo.http import request

from .. import const, utils

_logger = logging.getLogger(__name__)


class ShopeeWebhookController(http.Controller):

    # ------------------------------------------------------------------
    # OAuth callback
    # ------------------------------------------------------------------

    @http.route('/shopee/auth/callback', type='http', auth='user', methods=['GET'])
    def auth_callback(self, code=None, shop_id=None, **kwargs):
        """Nhận authorization code từ Shopee sau khi user cho phép."""
        if not code or not shop_id:
            return request.render('web.login', {'error': 'Missing code or shop_id from Shopee.'})

        # Tìm config đang chờ kết nối theo partner_id
        ShopeeConfig = request.env['shopee.config'].sudo()
        # Shopee trả về shop_id, tìm config chưa có shop_id (draft state)
        config = ShopeeConfig.search([
            ('state', '=', const.CONFIG_STATE_DRAFT),
            ('shop_id', '=', False),
        ], limit=1)

        if not config:
            # Có thể shop đã được kết nối trước đó - cập nhật token
            config = ShopeeConfig.search([('shop_id', '=', str(shop_id))], limit=1)

        if not config:
            _logger.warning('Shopee OAuth callback: no matching config for shop_id=%s', shop_id)
            return request.redirect('/web#action=shopee_integration.action_shopee_config')

        try:
            config._set_tokens_from_auth(code, shop_id)
            _logger.info('Shopee shop %s authorized successfully.', config.name)
        except Exception as e:
            _logger.error('Shopee OAuth error: %s', e)
            return request.redirect('/web#action=shopee_integration.action_shopee_config')

        return request.redirect('/web#action=shopee_integration.action_shopee_config')

    # ------------------------------------------------------------------
    # Webhook endpoint
    # ------------------------------------------------------------------

    @http.route('/shopee/webhook', type='http', auth='none', methods=['POST'], csrf=False)
    def webhook(self, **kwargs):
        """Nhận và xử lý webhook events từ Shopee."""
        try:
            raw_body = request.httprequest.get_data()
            payload = json.loads(raw_body)
        except Exception as e:
            _logger.error('Shopee webhook: invalid payload - %s', e)
            return request.make_response('Bad Request', status=400)

        shop_id = payload.get('shop_id')
        timestamp = payload.get('timestamp')
        code = payload.get('code')

        # Verify signature
        if not self._verify_signature(request, raw_body, timestamp, shop_id):
            _logger.warning('Shopee webhook: invalid signature for shop_id=%s', shop_id)
            return request.make_response('Unauthorized', status=401)

        _logger.info('Shopee webhook received: code=%s shop_id=%s', code, shop_id)

        # Dispatch event
        try:
            self._dispatch_event(code, payload, shop_id)
        except Exception as e:
            _logger.error('Shopee webhook dispatch error: %s', e)

        # Luôn trả về 200 để Shopee không retry
        return request.make_response('OK', status=200)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _verify_signature(self, req, raw_body, timestamp, shop_id):
        """Xác minh chữ ký HMAC từ Shopee."""
        received_sign = req.httprequest.headers.get('Authorization', '')
        if not received_sign:
            # Một số phiên bản Shopee gửi trong query param
            received_sign = req.httprequest.args.get('sign', '')

        ShopeeConfig = req.env['shopee.config'].sudo()
        config = ShopeeConfig.search([('shop_id', '=', str(shop_id))], limit=1)
        if not config:
            return False

        # Shopee webhook signature: HMAC-SHA256(partner_key, partner_id + path + timestamp + shop_id + body)
        path = '/shopee/webhook'
        base_string = (
            f'{config.partner_id_shopee}{path}{timestamp}{shop_id}'
            + raw_body.decode('utf-8')
        )
        expected = utils.generate_signature(config.partner_key, base_string)
        return hmac.compare_digest(expected, received_sign)

    def _dispatch_event(self, code, payload, shop_id):
        """Điều phối xử lý theo loại event."""
        env = request.env(user=request.env.ref('base.user_root').id)
        config = env['shopee.config'].search([('shop_id', '=', str(shop_id))], limit=1)
        if not config:
            return

        if code == const.WEBHOOK_CODE_ORDER:
            env['shopee.order']._process_order_event(payload)

        elif code == const.WEBHOOK_CODE_ITEM:
            _logger.info('Shopee product update event received for shop %s', shop_id)

        elif code == const.WEBHOOK_CODE_SHOP_DEAUTH:
            config.write({'state': const.CONFIG_STATE_EXPIRED})
            _logger.warning('Shopee shop %s deauthorized.', config.name)

        elif code == const.WEBHOOK_CODE_SHOP_AUTH:
            _logger.info('Shopee shop %s re-authorized via webhook.', config.name)
