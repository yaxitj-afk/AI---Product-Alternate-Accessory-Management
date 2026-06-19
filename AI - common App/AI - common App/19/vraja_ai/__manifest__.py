# -*- coding: utf-8 -*-
{  
    # App information
    'name': 'AI Agent',
    'category': 'Tools',
    'version': '19.0.1.0',
    'sequence': 1,
    'summary': """AI Agent serves as the foundation for all AI-powered applications within the Vraja AI ecosystem.        
                It provides a centralized platform to manage AI configurations, reusable templates, and activity logs across multiple AI solutions. 
                Whether you are using AI-powered product recommendations, forecasting, stock analysis, pricing intelligence, or other AI features, Vraja AI ensures a consistent and seamless experience.
                """,
    'license': 'OPL-1',
    'description': """""",

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
    'images': ['static/description/cover.gif'],

    # Author
    'author': 'Vraja Technologies',
    'maintainer': 'Vraja Technologies',
    'website': 'www.vrajatechnologies.com',
    'live_test_url': 'http://www.vrajatechnologies.com/contactus',

    #Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '',
    'currency': 'EUR',
}
