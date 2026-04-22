BASE_URL = 'https://partner.shopeemobile.com'
SANDBOX_URL = 'https://partner.test-stable.shopeemobile.com'

AUTH_URL = '/api/v2/shop/auth_partner'
TOKEN_URL = '/api/v2/auth/token/get'
REFRESH_TOKEN_URL = '/api/v2/auth/access_token/get'

# Order API
ORDER_LIST_URL = '/api/v2/order/get_order_list'
ORDER_DETAIL_URL = '/api/v2/order/get_order_detail'

# Product API
ITEM_LIST_URL = '/api/v2/product/get_item_list'
ITEM_DETAIL_URL = '/api/v2/product/get_item_detail_list'
ADD_ITEM_URL = '/api/v2/product/add_item'
UPDATE_ITEM_URL = '/api/v2/product/update_item'
UPDATE_STOCK_URL = '/api/v2/product/update_stock'
UPDATE_PRICE_URL = '/api/v2/product/update_price'

# Shopee order statuses
ORDER_STATUS_UNPAID = 'UNPAID'
ORDER_STATUS_READY_TO_SHIP = 'READY_TO_SHIP'
ORDER_STATUS_PROCESSED = 'PROCESSED'
ORDER_STATUS_SHIPPED = 'SHIPPED'
ORDER_STATUS_COMPLETED = 'COMPLETED'
ORDER_STATUS_IN_CANCEL = 'IN_CANCEL'
ORDER_STATUS_CANCELLED = 'CANCELLED'
ORDER_STATUS_INVOICE_PENDING = 'INVOICE_PENDING'

ORDER_STATUSES = [
    (ORDER_STATUS_UNPAID, 'Chờ thanh toán'),
    (ORDER_STATUS_READY_TO_SHIP, 'Chờ lấy hàng'),
    (ORDER_STATUS_PROCESSED, 'Đang xử lý'),
    (ORDER_STATUS_SHIPPED, 'Đang giao'),
    (ORDER_STATUS_COMPLETED, 'Hoàn thành'),
    (ORDER_STATUS_IN_CANCEL, 'Đang hủy'),
    (ORDER_STATUS_CANCELLED, 'Đã hủy'),
    (ORDER_STATUS_INVOICE_PENDING, 'Chờ hóa đơn'),
]

# Webhook event codes
WEBHOOK_CODE_ORDER = 3
WEBHOOK_CODE_ITEM = 4
WEBHOOK_CODE_SHOP_DEAUTH = 15
WEBHOOK_CODE_SHOP_AUTH = 16

# Sync states
SYNC_STATE_SYNCED = 'synced'
SYNC_STATE_PENDING = 'pending'
SYNC_STATE_ERROR = 'error'

# Config states
CONFIG_STATE_DRAFT = 'draft'
CONFIG_STATE_AUTHORIZED = 'authorized'
CONFIG_STATE_EXPIRED = 'expired'

# Token expiry buffer (seconds before actual expiry to trigger refresh)
TOKEN_REFRESH_BUFFER = 3600

# Max orders per API call
ORDER_BATCH_SIZE = 50

# Max items per API call
ITEM_BATCH_SIZE = 50
