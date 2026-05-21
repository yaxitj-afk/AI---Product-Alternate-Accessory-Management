# -*- coding: utf-8 -*-
{  # App information
    'name': 'Product Alternate & Accessory AI Agent',
    'category': 'Inventory',
    'version': '19.0.1.0',
    'sequence': 1,
    'summary': """""",


    'description': """""",
    'license': 'OPL-1',

    # Dependencies
    'depends': ['stock', 'vraja_ai','website_sale'],

    'external_dependencies': {
        'python': ['xlsxwriter'],
    },

    # Views
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml'
    ],

    # JS/XML Assets for the Custom Print Button
    'assets': {
        'web.assets_backend': [
            'product_ai_agent_vts/static/src/js/product_ai_dashboard.js',
            'product_ai_agent_vts/static/src/xml/dashboard_template.xml',
        ],
    },

    # Odoo Store Specific
    'images': [],

    # Author
    'author': 'Vraja Technologies',
    'website': 'http://www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',

    #Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': '_post_init_generate_product_report',
    'price': '',
    'currency': 'EUR',
}
