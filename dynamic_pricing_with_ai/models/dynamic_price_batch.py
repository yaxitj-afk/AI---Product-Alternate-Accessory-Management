# -*- coding: utf-8 -*-

from odoo import models, fields
from odoo.exceptions import UserError

class DpBatch(models.Model):
    _name = 'vraja.dp.batch'
    _description = 'Dynamic Pricing AI Batch'
    _order = 'batch_index asc'
    _rec_name = 'name'

    # ── Identification ────────────────────────────────────────────────────────
    name = fields.Char(string='Batch', readonly=True,
                       help='Auto-generated name, e.g. "Batch 1 of 3".')
    card_id = fields.Many2one('vraja.ai.card', string='Card', ondelete='cascade',
                              help='The Dynamic Pricing card this batch belongs to.')

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft',   'Draft'),    # Waiting to be picked up by cron
        ('running', 'Running'),  # Currently being processed by cron
        ('done',    'Done'),     # Successfully processed
    ], default='draft', string='State')

    # ── Position in the batch sequence ───────────────────────────────────────
    batch_index    = fields.Integer(string='Batch #',
                                    help='1-based position in the full batch sequence.')
    total_batches  = fields.Integer(string='Total Batches',
                                    help='Total number of batches for this card run.')
    products_count = fields.Integer(string='Products',
                                    help='Number of product rows in this batch.')

    # ── Data ──────────────────────────────────────────────────────────────────
    csv_rows = fields.Text(
        string='CSV Rows',
        help='CSV slice for this batch (header + data rows). Uploaded to OpenAI on processing.',
    )
    result_json = fields.Text(
        string='Result JSON',
        help='Parsed AI result for this batch. Stored for audit purposes after processing.',
    )
    file_id = fields.Char(
        string='OpenAI File ID',
        help='Temporary file ID from OpenAI Files API. Cleared after the AI call completes.',
    )
    error_message = fields.Text(
        string='Error',
        help='Populated when the batch fails. Batch is reset to draft for the next cron retry.',
    )
    segment_rules_json = fields.Text(
        string='Segment Rules',
        help='Snapshot of segment configuration at the time this batch was created.',
    )

    def action_run_batch_manually(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('Only draft batches can be run manually.')
        self.env['vraja.ai.card'].action_cron_dp_run_analysis(batch_id=self.id)
