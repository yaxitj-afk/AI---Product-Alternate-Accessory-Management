from odoo import fields, models,api


class AiEmailGenerateLog(models.Model):
    _name = 'ai.email.tmpl.log'
    _description = 'AI Email Generate Log'
    _order = 'create_date desc'

    name = fields.Char(string="Reference", readonly=True, copy=False, default="New")

    mailing_id = fields.Many2one(
        comodel_name='mailing.mailing',
        string="Mailing",
        ondelete='cascade',
    )
    provider = fields.Char(string="Provider")
    llm_model = fields.Char(string="Model")
    output_type = fields.Selection(
        selection=[
            ('text_only', 'Text Only'),
            ('full_design', 'Full Design'),
        ],
        string="Generation Type",
    )
    generated_html = fields.Text(string="Generated Template")
    total_tokens = fields.Integer(
        string="Total Tokens",
        store=True,
    )
    state = fields.Selection(
        selection=[
            ('success', 'Success'),
            ('failed', 'Failed'),
        ],
        string="Status",
        default='success',
    )
    log_message = fields.Text(string="Log Message")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('ai.email.tmpl.log') or 'New'
        return super().create(vals_list)