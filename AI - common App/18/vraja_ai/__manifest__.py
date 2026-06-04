# -*- coding: utf-8 -*-
{  # App information
    'name': 'Vraja AI',
    'category': 'Tools',
    'version': '18.0.1.0',
    'sequence': 1,
    'summary': """ """,
    'description': """ """,
    'license': 'OPL-1',

    # Dependencies
    'depends': ['base', 'web'],

    # Views
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/vraja_ai_card.xml',
        'views/vraja_ai_config.xml',
        'views/vraja_ai_log_view.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'vraja_ai/static/src/js/dashboard_client_action.js',
            'vraja_ai/static/src/xml/dashboard_template.xml',
        ],
    },

    # Odoo Store Specific
    'images': [''],

    # Author
    'author': 'Vraja Technologies',
    'maintainer': 'Vraja Technologies',
    'website': 'www.vrajatechnologies.com',

    #Technical
    'live_test_url': 'http://www.vrajatechnologies.com/contactus',
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '',
    'currency': 'EUR',
}