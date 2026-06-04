# -*- coding: utf-8 *-*
from odoo import models, fields, api


class VrajaAILog(models.Model):
    _name = 'vraja.ai.log'
    _description = 'Vraja AI Log'
    _order = 'run_date desc'

    name = fields.Char(string='Reference', readonly=True, default='New')
    run_date = fields.Datetime(string='Run Date', default=fields.Datetime.now, readonly=True)
    vraja_common_log_store = fields.Selection(selection=[],  string='AI Feature')
    status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], string='Status', readonly=True)
    line_ids = fields.One2many('vraja.ai.log.line', 'log_id', string='Log Lines')


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('vraja.ai.log')
        return super().create(vals_list)


class VrajaAILogLine(models.Model):
    _name = 'vraja.ai.log.line'
    _description = 'Vraja AI Log Line'

    log_id = fields.Many2one(
        'vraja.ai.log',
        string='Log',
        ondelete='cascade'
    )
