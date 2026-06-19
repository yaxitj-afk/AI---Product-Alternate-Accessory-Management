{
    'name': "AI Email Template Generator",
    'version': '19.0.1.0.0',
    'category': 'Marketing/Email Marketing',
    'summary': "Generate Email Marketing templates using AI (OpenAI, Claude, Gemini)",
    'description': """
            AI Email Template Generator
            ============================
            This module adds an AI-powered template generator inside the
            Email Marketing "New Mailing" screen.
            
            Features
            --------
            - Configure AI Provider (OpenAI / Anthropic Claude / Google Gemini)
            - Enter a simple text prompt describing the email campaign
            - Choose Text Only or Full Design generation
            - Generated content is placed directly into the mailing body
            - Simple step-by-step progress animation while AI is working
        """,

    'author': "Vraja Technologies",
    'depends': ['mass_mailing'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/mailing_mailing_views.xml',
        'views/ai_provider_config_views.xml',
        'wizard/ai_email_generate_wizard_views.xml',
        'views/email_template_log_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ai_email_template_generator/static/src/css/ai_generate.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
