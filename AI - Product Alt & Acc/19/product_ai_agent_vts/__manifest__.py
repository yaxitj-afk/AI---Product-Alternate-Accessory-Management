# -*- coding: utf-8 -*-
{  # App information
    'name': 'AI Product Alternate & Accessory | AI-Powered Product Recommendation | Smart Product Linking with OpenAI in Odoo',
    'category': 'Inventory',
    'version': '19.0.1.0',
    'sequence': 1,
    'summary': """
        Complete AI-powered solution for automatically analysing your product caalog and recommending the most relevant alternative and accessory products for each item.
        Integrates with OpenAI and supports multiple LLM models including GPT-4.1,GPT-4.1 Mini, GPT-5, GPT-5 Mini, GPT-5.4, and GPT-5.4 Mini.
        Clean 6-step guided workflow to select products, configure AI settings, run the analysis, and review and apply the results from a single interface.
        Uses product category, tags, price, attributes, and real sales co-purchase history as data sources for generating intelligent product relationship suggestions.
        Supports bulk product selection through manual search, Select All, or Excel file import using Internal Reference.
        Configurable AI settings including Suggestion Type, Minimum Confidence Level,Price Tolerance, and Maximum Suggestions per Product.
        Scheduled Auto Run via cron jobs to automatically run the AI analysis daily without any manual intervention.
        Dedicated AI Logs section with complete run history including status, configuration used, tokens consumed, and per-product breakdown of all suggestions applied.
        AI-generated suggestions are applied directly to the Accessory Products and Alternative Products fields on each product record for immediate upselling andcross-selling.
        AI Product Recommendation for Odoo
        AI-Powered Product Alternate & Accessory Linking
        Smart Product Relationship Management with OpenAI
        Automated Alternative & Accessory Product Suggestions
        OpenAI Product Catalog Analysis in Odoo
        AI Cross-Sell and Upsell Product Recommendations
        Product Alternate Suggestion using GPT in Odoo
        Odoo AI Product Accessory Linking
        Smart Product Catalog Management with AI
        AI-Based Product Relationship Builder for Odoo
        Automated Product Upsell & Cross-Sell Management
        OpenAI Integration for Product Recommendations in Odoo
        GPT-Powered Product Alternate & Accessory Module
        AI Product Linking and Recommendation System for Odoo
        Intelligent Product Catalog Optimization with OpenAI
    """,

    'description': """""",
    'license': 'OPL-1',

    # Dependencies
    'depends': ['vraja_ai', 'website_sale'],

    'external_dependencies': {
        'python': ['xlsxwriter', 'openpyxl', 'requests'],
        # xlsxwriter :- Used when creating Excel (.xlsx) files from scratch.
        # openpyxl :- Used when reading or modifying existing Excel files.
        # requests :- Used for calling external APIs or websites.
    },

    # Views
    'data': [
        'data/cron.xml',
        'views/product_ai_log_view.xml',
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

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': '_post_init_generate_product_card',
    'uninstall_hook': '_uninstall_product_alt_acc_ai',
    'price': '',
    'currency': 'EUR',
}
