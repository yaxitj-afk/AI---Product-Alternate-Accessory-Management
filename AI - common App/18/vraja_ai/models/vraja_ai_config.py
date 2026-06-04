# -*- coding: utf-8 -*-
from odoo import fields, models


class VrajaAIConfig(models.Model):
    _name = 'vraja.ai.config'
    _description = 'VRAJA AI Configuration'
    _rec_name = 'openai_api_key'

    name = fields.Char(string="Name")
    openai_api_key = fields.Char(string='ChatGPT Key')
    llm_model = fields.Selection(
        selection=[
            ('gpt-4.1', 'GPT-4.1'),
            ('gpt-4.1-mini', 'GPT-4.1 Mini'),
            ('gpt-5', 'GPT-5'),
            ('gpt-5-mini', 'GPT-5 Mini'),
            ('gpt-5.4', 'GPT-5.4'),
            ('gpt-5.4-mini', 'GPT-5.4 Mini'),
        ],
        string="LLM Model",
        default='gpt-5.4',
        required=True,
    )