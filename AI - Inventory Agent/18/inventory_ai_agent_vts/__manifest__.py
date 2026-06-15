# -*- coding: utf-8 -*-
{  # App information
    'name': 'AI Inventory Replenishment Agent | Forecast, Vendor & RFQ Intelligence',
    'category': 'Inventory',
    'version': '18.0.1.0',
    'summary': """Inventory AI Agent helps purchase and inventory teams identify products that need replenishment before stockouts occur.
                The module prepares stock, sales, and purchase history in an Excel workbook, sends the workbook to the configured Vraja AI/OpenAI setup, and returns practical replenishment recommendations. Users can review recommended products, forecast quantities, suggested vendors, and then create draft RFQs directly from the AI result.

                Key Features:
                - AI low stock replenishment dashboard
                - Stock, incoming, outgoing, and available quantity analysis
                - Sales forecast period configuration
                - Purchase history and vendor performance review
                - Vendor recommendation based on lead time, delay, reliability, and price signals
                - Manual or scheduled workbook generation
                - Manual or scheduled AI analysis
                - Draft RFQ creation from recommendation rows
                - Inventory AI run logs with success/failure status and recommended product lines

                odoo ai inventory, inventory ai agent, stock replenishment ai, ai procurement, purchase planning ai, inventory forecasting, 
                demand forecasting, inventory optimization, low stock alert, stock prediction, rfq automation, purchase recommendation, 
                vendor recommendation, inventory management ai, procurement ai, warehouse ai, stock forecasting, inventory replenishment, 
                purchase order ai, openai inventory
                """,
    'license': 'OPL-1',
    'description': """AI-powered low stock forecasting, vendor recommendation, and RFQ automation for Odoo Inventory.""",

    # Dependencies
    'depends': ['sale_management', 'purchase_stock', 'vraja_ai'],

    'external_dependencies': {
        'python': ['openpyxl', 'requests', 'xlsxwriter'],
    },

    # Views
    'data': [
        'security/ir.model.access.csv',
        'views/inventory_ai_log_view.xml',
        'data/ir_cron.xml',
    ],

    # JS/XML Assets for the Custom Print Button
    'assets': {
        'web.assets_backend': [
            'inventory_ai_agent_vts/static/src/js/vraja_ai_dashboard_patch.js',
            'inventory_ai_agent_vts/static/src/css/inventory_ai_dashboard.css',
            'inventory_ai_agent_vts/static/src/xml/dashboard_template.xml',
        ],
    },

    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    'author': 'Vraja Technologies',
    'website': 'www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',
    'live_test_url': 'http://www.vrajatechnologies.com/contactus',

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': '_post_init_generate_inventory_report',
    'uninstall_hook': '_uninstall_low_stock_ai_analysis',
    'price': '49',
    'currency': 'EUR',
}
