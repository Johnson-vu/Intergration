{
    'name': 'Shopee Integration',
    'version': '18.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Tích hợp sàn Shopee với Odoo - Đồng bộ sản phẩm, đơn hàng và tồn kho',
    'description': """
        Module tích hợp Shopee Open Platform API với hệ thống Odoo 18.

        Tính năng:
        - Quản lý nhiều shop Shopee (đa công ty)
        - OAuth 2.0 authorization flow
        - Đồng bộ sản phẩm hai chiều (Odoo ↔ Shopee)
        - Kéo đơn hàng từ Shopee về Odoo tự động
        - Đồng bộ tồn kho theo thời gian thực
        - Webhook nhận sự kiện từ Shopee (đơn hàng, sản phẩm)
        - Cron job tự động đồng bộ định kỳ
    """,
    'author': 'Johnson Vu',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'sale_management',
        'stock',
        'product',
        'account',
    ],
    'data': [
        'security/shopee_security.xml',
        'security/ir.model.access.csv',
        'data/shopee_cron.xml',
        'views/shopee_config_views.xml',
        'views/shopee_product_mapping_views.xml',
        'views/shopee_order_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
        'wizard/shopee_sync_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
