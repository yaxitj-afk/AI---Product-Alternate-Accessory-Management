# -*- coding: utf-8 -*-
{  # App information
    'name': 'AI Dynamic Pricing Agent | AI Dynamic Pricing',
    'category': 'Inventory',
    'version': '18.0.1.0',
    'sequence': 1,
    'summary': """""",

    'description': """""",
    'license': 'OPL-1',

    # Dependencies
    'depends': ['vraja_ai', 'website_sale','stock'],

    # Views
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/dynamic_price_log_view.xml',
        'views/dynamic_pricing_batch_view.xml',
    ],

    # JS/XML Assets for the Custom Print Button
    'assets': {
        'web.assets_backend': [
            'dynamic_pricing_with_ai/static/src/css/dynamic_pricing_dashboard.css',
            'dynamic_pricing_with_ai/static/src/css/dp_analysis_dashboard.css',
            'dynamic_pricing_with_ai/static/src/js/dynamic_pricing_card_dashboard.js',
            'dynamic_pricing_with_ai/static/src/js/dp_analysis_dashboard.js',
            'dynamic_pricing_with_ai/static/src/xml/dp_dashboard_template.xml',
            'dynamic_pricing_with_ai/static/src/xml/dp_analysis_dashboard_template.xml',
        ],
    },

    # Odoo Store Specific
    'images': [],

    # Author
    'author': 'Vraja Technologies',
    'website': 'http://www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': '_post_init_generate_dynamic_price_card',
    'uninstall_hook': '_uninstall_dynamic_pricing_with_ai',
    'price': '',
    'currency': 'EUR',
}
