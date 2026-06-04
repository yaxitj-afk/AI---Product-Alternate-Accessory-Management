# -*- coding: utf-8 -*-

from odoo import models, api, fields
from odoo.exceptions import UserError
import json
import requests
import logging
import pytz
from datetime import datetime, timedelta, time
from collections import defaultdict

_logger = logging.getLogger(__name__)


class VrajaAICard(models.Model):
    _inherit = 'vraja.ai.card'

    vraja_common_store = fields.Selection(
        selection_add=[('dynamic_pricing', 'Dynamic Pricing with AI')]
    )

    # ── Products ──────────────────────────────────────────────────────────────
    dp_selected_product_ids = fields.Many2many(
        'product.template',
        'vraja_card_dp_product_rel',
        'card_id', 'product_id',
        string='Selected Products',
        store=True,
        domain=[('active', '=', True), ('sale_ok', '=', True)],
    )

    # ── Target Pricelists (card level — applied when writing prices) ──────────
    dp_pricelist_ids = fields.Many2many(
        'product.pricelist',
        'vraja_card_dp_pricelist_rel',
        'card_id', 'pricelist_id',
        string='Target Pricelists',
    )

    # ── Competitor URLs ───────────────────────────────────────────────────────
    dp_competitor_url_1 = fields.Char(string='Competitor URL 1')
    dp_competitor_url_2 = fields.Char(string='Competitor URL 2')
    dp_competitor_url_3 = fields.Char(string='Competitor URL 3')

    # ── Global pricing guardrails (used as defaults for segments) ─────────────
    dp_min_margin_pct = fields.Float(
        string='Min Margin (%)', default=15.0,
        help='AI will never suggest a price that gives margin below this. Acts as price floor.',
    )
    dp_max_margin_pct = fields.Float(
        string='Max Margin (%)', default=60.0,
        help='AI will never suggest a price that gives margin above this. Acts as price ceiling.',
    )
    dp_max_increase_pct = fields.Float(
        string='Max Price Increase (%)', default=10.0,
        help='Maximum % the AI can increase price in one run.',
    )
    dp_max_decrease_pct = fields.Float(
        string='Max Price Decrease (%)', default=20.0,
        help='Maximum % the AI can decrease price in one run.',
    )

    # ── Thresholds ────────────────────────────────────────────────────────────
    dp_dead_stock_days = fields.Integer(
        string='Dead Stock Days', default=45,
        help='Days without any sale before a product is flagged as dead stock.',
    )
    dp_sales_history_days = fields.Integer(
        string='Sales History Days', default=30,
        help='How many recent days of sales to include in the analysis.',
    )

    # ── Business context & prompts ────────────────────────────────────────────
    dp_auto_apply = fields.Boolean(string='Auto Apply via Cron', default=False)
    dp_cron_time = fields.Char(string='Cron Run Time', default='02:00 AM')
    dp_business_info = fields.Text(string='Business Context')

    dp_ai_instruction = fields.Text(
        string='AI System Instruction',
        default=lambda self: self._default_dp_ai_instruction(),
    )
    dp_ai_prompt = fields.Text(
        string='AI User Prompt',
        default=lambda self: self._default_dp_ai_prompt(),
    )
    dp_segment_rules_json = fields.Text(string='Segment Rules JSON', default='[]')

    # ── Status & results ──────────────────────────────────────────────────────
    dp_status = fields.Selection([
        ('idle', 'Idle'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], default='idle', string='Status')

    dp_segment_type_options = fields.Selection([
        ('retailer', 'Retailer'),
        ('wholesaler', 'Wholesaler'),
        ('b2b', 'B2B'),
        ('b2c', 'B2C'),
        ('vip', 'VIP'),
        ('distributor', 'Distributor'),
        ('walkin', 'Walk-in'),
    ], string='Segment Type')

    dp_result_json = fields.Text(string='AI Result JSON', readonly=True)
    dp_raw_result = fields.Text(string='AI Raw Result', readonly=True)
    dp_error = fields.Text(string='Error', readonly=True)
    dp_analyzed_on = fields.Date(string='Last Analysed On', readonly=True)
    dp_last_tokens = fields.Integer(string='Last Tokens Used', default=0, readonly=True)

    # =========================================================================
    # DEFAULT PROMPTS
    # =========================================================================

    @api.model
    def _default_dp_ai_instruction(self):
        return """\
You are a pricing engine. Decide the optimal price for every product × segment pair.
 
RULES (never break):
- floor   = cost_price / (1 - min_margin_pct / 100)
- ceiling = cost_price / (1 - max_margin_pct / 100)
- price_min = max(floor,   current_price * (1 - max_decrease_pct / 100))
- price_max = min(ceiling, current_price * (1 + max_increase_pct / 100))
- suggested_price must be within [price_min, price_max], rounded to 2dp.
- suggested_price must always be > cost_price.
- cost_price = 0 → decision = "skip", reason = "Cost price missing."
- floor > ceiling → decision = "skip", reason = "Invalid margin band."
- margin_before = (current_price - cost_price) / current_price * 100, rounded 2dp.
- margin_after  = (suggested_price - cost_price) / suggested_price * 100, rounded 2dp.
- decision must be: increase / decrease / hold / skip.
- Return JSON array only. No markdown. No extra text.
- Every product × segment pair from input must appear in output.
"""

    @api.model
    def _default_dp_ai_prompt(self):
        return """\
   Decide the best price for every product × segment pair using all signals together.
 
STEP 1 — COMPETITOR (only if URLs given):
- Estimate market price from URL and product category using your knowledge.
- If market price found → use it as pricing anchor in Step 2.
- If market price not found → rely on Step 2 signals only.
 
STEP 2 — DECIDE using ALL signals together:
- stock_status = out_of_stock
    → hold always. No pricing action when stock is zero.
 
- cost_price = 0 or floor > ceiling
    → skip.
 
- competitor anchor found:
    market > current_price AND stock_status != out_of_stock → increase toward market, cap at price_max.
    market < current_price                                  → decrease toward market, cap at price_min.
    market within 5% of current_price                      → ignore competitor, use demand signals below.
 
- No competitor anchor OR competitor within 5%:
    days_no_sale = null (never sold)                        → suggested_price = floor.
    days_no_sale > dead_stock_days AND overstock            → decrease to price_min.
    days_no_sale > dead_stock_days AND in_stock             → decrease by 50% of max_decrease_pct.
    days_no_sale > dead_stock_days AND low_stock            → hold.
    overstock AND avg_qty_per_day >= 1.0                   → hold.
    overstock AND avg_qty_per_day < 1.0                    → decrease toward price_min.
    avg_qty_per_day >= 1.0 AND stock in (in_stock,low_stock)→ increase toward price_max.
    avg_qty_per_day >= 0.3                                  → hold.
    avg_qty_per_day < 0.3 AND low_stock                    → hold.
    avg_qty_per_day < 0.3 AND in_stock                     → decrease slightly (30% of max_decrease_pct).
 
STEP 3 — CLAMP:
- Always clamp final price to [price_min, price_max].
- Round to 2 decimal places.
 
OUTPUT — one object per product × segment:
[{
  "product_id": int,
  "product_name": str,
  "segment_name": str,
  "current_price": float,
  "suggested_price": float,
  "decision": "increase|decrease|hold|skip",
  "margin_before": float,
  "margin_after": float,
  "reason": "one sentence — key signals used"
}]
"""

    # =========================================================================
    # DASHBOARD ROUTING
    # =========================================================================

    def action_review_dashboard(self):
        action = super().action_review_dashboard()
        self.ensure_one()
        if self.vraja_common_store == 'dynamic_pricing':
            action['tag'] = 'dynamic_pricing_dashboard_template'
        return action

    def action_log_view(self):
        action = super().action_log_view()
        if self.vraja_common_store == 'dynamic_pricing':
            action['name'] = 'Dynamic Pricing Logs'
            action['views'] = [(False, 'list'),
                               (self.env.ref('dynamic_pricing_with_ai.dynamic_pricing_ai_log_form_view').id, 'form'), ]
            action['context'] = {'search_default_filter_dynamic_pricing_ai': 1, 'create': False}
        return action

    @api.model
    def action_dp_get_default_card_id(self):
        card = self.sudo().search(
            [('vraja_common_store', '=', 'dynamic_pricing')], limit=1
        )
        return card.id if card else False

    # =========================================================================
    # SIGNAL COMPUTATION
    # =========================================================================

    def _compute_product_signals(self, product):
        self.ensure_one()
        history_days = max(self.dp_sales_history_days or 30, 1)
        dead_stock_days = self.dp_dead_stock_days or 45
        date_from = fields.Date.subtract(fields.Date.today(), days=history_days)

        total_qty, _, _ = self._get_sales_history(product, date_from)
        avg_qty = round(total_qty / history_days, 4)
        stock_status, qty_on_hand = self._get_stock_status(product)
        days_no_sale = self._get_days_no_sale(product)

        return {
            'product_id': product.id,
            'product_name': product.name,
            'category': product.categ_id.complete_name or 'Uncategorized',
            'cost_price': product.standard_price or 0.0,
            'current_price': product.list_price or 0.0,
            'avg_qty_per_day': avg_qty,
            'stock_status': stock_status,
            'qty_on_hand': qty_on_hand,
            'days_no_sale': days_no_sale,
            'dead_stock_days': dead_stock_days,
        }

    def _compute_hint(self, cost, price, avg_qty, stock_status, days_no_sale, dead_stock_days):
        if cost <= 0 or price <= 0:  # CASE 1 — missing cost or price → skip
            return 'skip'

        if stock_status == 'out_of_stock':  # CASE 2 — out of stock → never change price
            return 'hold'

        if days_no_sale is None:  # CASE 3 — never sold before → price at floor
            return 'decrease'

        if days_no_sale > dead_stock_days and stock_status == 'overstock':  # CASE 4 — dead stock + overstock → aggressive decrease
            return 'decrease'

        if days_no_sale > dead_stock_days and stock_status == 'in_stock':  # CASE 5 — dead stock + in_stock → moderate decrease
            return 'decrease'

        if days_no_sale > dead_stock_days and stock_status == 'low_stock':  # CASE 6 — dead stock + low_stock → hold (no need to push further)
            return 'hold'

        if stock_status == 'overstock' and avg_qty >= 1.0:  # CASE 7 — overstock + high demand → hold (demand will clear stock)
            return 'hold'

        if stock_status == 'overstock':  # CASE 8 — overstock + low/moderate demand → decrease to clear
            return 'decrease'

        if avg_qty >= 1.0:  # CASE 9 — high demand + any healthy stock → increase
            return 'increase'

        if avg_qty >= 0.3:  # CASE 10 — moderate demand → hold
            return 'hold'

        if stock_status == 'low_stock':  # CASE 11 — low demand + low stock → hold (no need to decrease)
            return 'hold'

        return 'decrease'  # CASE 12 — low demand + normal stock → small decrease to stimulate

    # ── Signal helpers ────────────────────────────────────────────────────────
    def _get_sales_history(self, product, date_from):
        """Returns (total_qty_sold, total_revenue, order_count)."""
        recent_orders = self.env['sale.order'].sudo().search([
            ('date_order', '>=', date_from),
            ('state', 'in', ['sale', 'done']),
        ])
        lines = self.env['sale.order.line'].sudo().search([
            ('product_id.product_tmpl_id', '=', product.id),
            ('order_id', 'in', recent_orders.ids),
        ])
        total_qty = sum(lines.mapped('product_uom_qty'))
        total_revenue = sum(l.product_uom_qty * l.price_unit for l in lines)
        order_count = len(set(lines.mapped('order_id').ids))
        return round(total_qty, 4), round(total_revenue, 4), order_count

    def _get_stock_status(self, product):
        """
        Returns (stock_status_string, qty_on_hand).
        Compares qty on hand to the reorder point configured for the product.
        Falls back to 10 units if no reorder rule is set.
        """
        quants = self.env['stock.quant'].sudo().search([
            ('product_id.product_tmpl_id', '=', product.id),
            ('location_id.usage', '=', 'internal'),
        ])
        qty = sum(quants.mapped('quantity'))

        orderpoint = self.env['stock.warehouse.orderpoint'].sudo().search([
            ('product_id.product_tmpl_id', '=', product.id),
        ], limit=1)
        reorder_qty = orderpoint.product_min_qty if orderpoint else 10.0

        if qty <= 0:
            status = 'out_of_stock'
        elif qty < reorder_qty:
            status = 'low_stock'
        elif qty <= reorder_qty * 3:
            status = 'in_stock'
        else:
            status = 'overstock'

        return status, round(qty, 2)

    def _get_days_no_sale(self, product):
        """Returns number of days since last confirmed sale, or None if never sold."""
        product_ids = product.product_variant_ids.ids
        last_order = self.env['sale.order'].sudo().search([
            ('state', 'in', ['sale', 'done']),
            ('order_line.product_id', 'in', product_ids),
        ], order='date_order desc', limit=1)

        if last_order and last_order.date_order:
            return (fields.Date.today() - last_order.date_order.date()).days
        return None

    # =========================================================================
    # PROMPT BUILDER
    # =========================================================================

    def _build_dp_prompt(self, products_data, segments):
        self.ensure_one()
        business = "BUSINESS: " + (self.dp_business_info or "Not provided.")

        urls = [u for u in [
            self.dp_competitor_url_1,
            self.dp_competitor_url_2,
            self.dp_competitor_url_3,
        ] if u and u.strip()]
        competitor = ("COMPETITOR URLS:\n" + "\n".join(f"  {i + 1}. {u}" for i, u in enumerate(urls))
            if urls else "COMPETITOR URLS: None. Use demand signals only."
        )

        segment_rows = [{
            'segment_name': seg.get('customer_type', 'Unnamed'),
            'min_margin_pct': seg.get('min_margin_pct', self.dp_min_margin_pct or 15.0),
            'max_margin_pct': seg.get('max_margin_pct', self.dp_max_margin_pct or 60.0),
            'max_increase_pct': seg.get('max_increase_pct', self.dp_max_increase_pct or 10.0),
            'max_decrease_pct': seg.get('max_decrease_pct', self.dp_max_decrease_pct or 20.0),
        } for seg in segments]

        segments_block = "SEGMENTS:\n" + json.dumps(segment_rows, indent=2)
        products_block = "PRODUCTS:\n" + json.dumps(products_data, indent=2)

        expected = len(products_data) * len(segment_rows)
        reminder = (
            f"Return {expected} rows "
            f"({len(products_data)} products × {len(segment_rows)} segments). "
            "JSON only."
        )

        return "\n\n".join([self.dp_ai_prompt,business,competitor,segments_block,products_block,reminder,])

    # =========================================================================
    # AI API CALL
    # =========================================================================

    def _call_dp_ai_api(self, system_prompt, user_prompt):
        """Calls OpenAI /v1/responses and returns (raw_text, total_tokens)."""
        config = self.env['vraja.ai.config'].sudo().search([], limit=1)
        if not config or not config.openai_api_key:
            raise UserError('OpenAI API key is not configured. Please configure it first.')
        print('prompt :- ====== ', system_prompt, user_prompt)

        try:
            response = requests.post(
                'https://api.openai.com/v1/responses',
                json={
                    'model': config.llm_model,
                    'input': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_prompt},
                    ],
                },
                headers={
                    'Authorization': f'Bearer {config.openai_api_key}',
                    'Content-Type': 'application/json',
                },
                timeout=120,
            )

            response.raise_for_status()
            body = response.json()
            tokens = body.get('usage', {}).get('total_tokens', 0)
            text = body['output'][0]['content'][0]['text']
            _logger.info('DP AI response tokens: %s', tokens)
            return text, tokens

        except requests.exceptions.Timeout:
            raise UserError('OpenAI API timed out. Please try again.')
        except requests.exceptions.ConnectionError:
            raise UserError('Cannot connect to OpenAI. Check your internet connection.')
        except requests.exceptions.RequestException as e:
            raise UserError(f'API request failed: {e}')
        except (KeyError, IndexError, TypeError) as e:
            raise UserError(f'Unexpected response format from OpenAI: {e}')

    # =========================================================================
    # RESPONSE PARSER
    # =========================================================================

    def _parse_dp_ai_response(self, raw_text):
        """
        Parses the AI JSON array.
        Returns a list of dicts, one per product × segment row.
        """
        text = raw_text.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[-1]
            text = text.rsplit('```', 1)[0].strip()

        try:
            items = json.loads(text)
        except json.JSONDecodeError as e:
            raise UserError(
                f'AI returned invalid JSON: {e}\n\nRaw response:\n{raw_text[:500]}'
            )

        if not isinstance(items, list):
            raise UserError('AI response was not a JSON array as required.')

        results = []
        for item in items:
            if not item.get('product_id'):
                continue
            results.append({
                'product_id': int(item['product_id']),
                'product_name': item.get('product_name', ''),
                'segment_name': item.get('segment_name', ''),
                'current_price': float(item.get('current_price', 0)),
                'suggested_price': float(item.get('suggested_price', 0)),
                'decision': item.get('decision', 'hold'),
                'margin_before': float(item.get('margin_before', 0)),
                'margin_after': float(item.get('margin_after', 0)),
                'reason': item.get('reason', ''),
            })
        return results

    # =========================================================================
    # DASHBOARD DATA — JS Interface
    # =========================================================================

    def get_dp_dashboard_data(self):
        """Returns all data needed to populate the Dynamic Pricing dashboard."""
        self.ensure_one()
        segment_field = self.fields_get(['dp_segment_type_options'])
        segment_options = segment_field.get('dp_segment_type_options', {}).get('selection', [])

        return {
            'id': self.id,
            'dp_status': self.dp_status,
            'dp_analyzed_on': self.dp_analyzed_on and str(self.dp_analyzed_on) or False,
            'dp_last_tokens': self.dp_last_tokens or 0,
            'dp_min_margin_pct': self.dp_min_margin_pct,
            'dp_max_margin_pct': self.dp_max_margin_pct,
            'dp_max_increase_pct': self.dp_max_increase_pct,
            'dp_max_decrease_pct': self.dp_max_decrease_pct,
            'dp_dead_stock_days': self.dp_dead_stock_days,
            'dp_sales_history_days': self.dp_sales_history_days,
            'dp_auto_apply': self.dp_auto_apply,
            'dp_cron_time': self.dp_cron_time or '02:00 AM',
            'dp_business_info': self.dp_business_info or '',
            'dp_result_json': self.dp_result_json or '',
            'dp_error': self.dp_error or '',
            'dp_competitor_url_1': self.dp_competitor_url_1 or '',
            'dp_competitor_url_2': self.dp_competitor_url_2 or '',
            'dp_competitor_url_3': self.dp_competitor_url_3 or '',
            'dp_segment_rules': json.loads(self.dp_segment_rules_json or '[]'),
            'dp_segment_type_options': [
                {'value': v, 'label': l} for v, l in segment_options
            ],
            'pricelist_ids': [
                {'id': pl.id, 'name': pl.name} for pl in self.dp_pricelist_ids
            ],
            'selected_products': [
                {'id': p.id, 'name': p.name}
                for p in self.dp_selected_product_ids
            ],
        }

    def action_save_dp_dashboard_data(self, values):
        self.ensure_one()

        scalar_fields = [
            'dp_min_margin_pct', 'dp_max_margin_pct',
            'dp_max_increase_pct', 'dp_max_decrease_pct',
            'dp_dead_stock_days', 'dp_sales_history_days',
            'dp_auto_apply', 'dp_business_info',
            'dp_competitor_url_1', 'dp_competitor_url_2', 'dp_competitor_url_3',
            'dp_cron_time',
        ]
        write_vals = {k: v for k, v in values.items() if k in scalar_fields}

        if 'dp_selected_product_ids' in values:
            write_vals['dp_selected_product_ids'] = [(6, 0, values['dp_selected_product_ids'])]
        if 'dp_pricelist_ids' in values:
            write_vals['dp_pricelist_ids'] = [(6, 0, values['dp_pricelist_ids'])]

        if 'dp_segment_rules' in values:
            rules = values['dp_segment_rules']
            # Assign a simple incremental id to each rule if missing
            for i, r in enumerate(rules):
                if not r.get('id'):
                    r['id'] = i + 1
            write_vals['dp_segment_rules_json'] = json.dumps(rules)

        self.sudo().write(write_vals)

        # Sync cron job active state and next call time,  Calling cron based on the timeing

        if 'dp_auto_apply' in write_vals or 'dp_cron_time' in write_vals:
            cron = self.env.ref(
                'dynamic_pricing_with_ai.ir_cron_dp_run_analysis',
                raise_if_not_found=False
            )
            if cron:
                cron_vals = {'active': self.dp_auto_apply}

                time_str = self.dp_cron_time or '02:00 AM'
                try:
                    t = datetime.strptime(time_str.strip(), '%I:%M %p')
                    user_tz = self.env.user.tz or 'UTC'
                    local_tz = pytz.timezone(user_tz)

                    now_local = datetime.now(local_tz)
                    next_call_local = now_local.replace(
                        hour=t.hour, minute=t.minute, second=0, microsecond=0
                    )

                    # If time already passed today, schedule for tomorrow
                    if next_call_local <= now_local:
                        next_call_local += timedelta(days=1)

                    # Convert to UTC for Odoo
                    next_call_utc = next_call_local.astimezone(pytz.utc).replace(tzinfo=None)
                    cron_vals['nextcall'] = next_call_utc

                except Exception as e:
                    _logger.warning('DP: Could not parse cron time "%s": %s', time_str, e)

                cron.sudo().write(cron_vals)

        return {'success': True}

    # =========================================================================
    # RUN AI ANALYSIS
    # segments live in the JS session and are passed as a parameter.
    # =========================================================================

    def action_run_dynamic_pricing(self, segments=None):
        """
        Called from the JS dashboard Run AI button.

        segments : list of dicts from JS, each with:
            {   segment_name     : str,
                pricelist_ids    : [int, ...],
                min_margin_pct   : float,
                max_margin_pct   : float,
                max_increase_pct : float,
                max_decrease_pct : float,     }

        Flow:
            1. Validate products and segments
            2. Compute signals (sales history + stock status + days no sale)
            3. Build the full prompt (products × segments + competitor URLs)
            4. Call OpenAI
            5. Parse and store the flat result list as JSON
        """
        self.ensure_one()
        self.sudo().write({'dp_status': 'running', 'dp_error': False})

        try:
            if not self.dp_selected_product_ids:
                raise UserError(
                    'No products selected. Please select products in Step 2 first.'
                )

            segments = segments or []
            if not segments:
                raise UserError(
                    'No segments defined. Please add at least one segment in Step 3.'
                )

            # Step 1 — compute signals for every selected product
            products_data = [
                self._compute_product_signals(p)
                for p in self.dp_selected_product_ids
            ]

            # Step 2 — build prompt
            user_prompt = self._build_dp_prompt(products_data, segments)

            # Step 3 — call AI
            raw_result, tokens = self._call_dp_ai_api(
                self.dp_ai_instruction or '', user_prompt
            )

            # Step 4 — parse and store
            parsed = self._parse_dp_ai_response(raw_result)
            self.sudo().write({
                'dp_raw_result': raw_result,
                'dp_result_json': json.dumps(parsed, ensure_ascii=False, indent=2),
                'dp_status': 'done',
                'dp_analyzed_on': fields.Date.today(),
                'dp_last_tokens': tokens,
            })


        except UserError as e:
            self.sudo().write({'dp_status': 'error', 'dp_error': str(e)})
            self._create_dp_log(status='failed', message=str(e))
            self.env.cr.commit()
            raise

        return True

    # =========================================================================
    # APPLY PRICING — writes to pricelists only, never to product fields
    # =========================================================================

    def action_apply_dynamic_pricing(self, segments=None):
        self.ensure_one()

        if not self.dp_result_json:
            return {'applied': 0}

        segments = segments or []

        # Build a quick lookup: segment_name → list of pricelist IDs
        seg_map = {
            seg.get('customer_type', ''): seg.get('pricelist_ids', [])
            for seg in segments
        }

        parsed = json.loads(self.dp_result_json)
        applied = 0
        skipped = 0
        errors = 0
        log_lines = []

        for row in parsed:
            decision = row.get('decision', 'hold')
            suggested_price = row.get('suggested_price', 0.0)
            segment_name = row.get('segment_name', '')
            product_id = row.get('product_id')

            if not product_id:
                continue

            product = self.env['product.template'].browse(int(product_id))

            # ── Skip if product no longer exists in DB ─────────────────────────
            if not product.exists():
                continue

            # ── Skip "hold" decisions and zero prices ──────────────────────────
            if decision == 'hold' or not suggested_price:
                skipped += 1
                continue

            # ── Skip if no pricelist mapped for this segment ───────────────────
            pricelist_ids = seg_map.get(segment_name, [])
            if not pricelist_ids:
                errors += 1
                continue

            # ── Write to every pricelist that belongs to this segment ──────────
            # Track if any pricelist write failed for this row
            row_has_error = False

            for pl_id in pricelist_ids:
                pricelist = self.env['product.pricelist'].browse(pl_id)

                # Skip if pricelist no longer exists in DB
                if not pricelist.exists():
                    continue

                try:
                    self._upsert_pricelist_item(pricelist, product, suggested_price)
                except Exception:
                    row_has_error = True
                    errors += 1

            if row_has_error:
                continue

            applied += 1
            log_lines.append(self._build_log_line(product, row, 'success'))

        # ── Reset card status ──────────────────────────────────────────────────
        self.sudo().write({'dp_status': 'idle'})

        # ── Create one DB log record with only successfully applied lines ───────
        if log_lines:
            self._create_dp_log(status='success',
                                message=f'Applied AI pricing to {applied} product–segment combination(s).',
                                log_lines=log_lines, total_tokens=self.dp_last_tokens or 0, applied=True,
                                pricelists_updated=applied, )

        return {'applied': applied, 'skipped': skipped, 'errors': errors}

    def _upsert_pricelist_item(self, pricelist, product, suggested_price):
        original_price = product.list_price

        if suggested_price >= original_price:
            price_vals = {
                'compute_price': 'fixed',
                'fixed_price': suggested_price,
            }

        else:
            if original_price > 0:
                percent_price = round((1.0 - suggested_price / original_price) * 100.0, 4)
            else:
                percent_price = 0.0

            price_vals = {
                'compute_price': 'percentage',
                'percent_price': percent_price,
            }

        existing_ai_line = self.env['product.pricelist.item'].sudo().search([
            ('pricelist_id', '=', pricelist.id),
            ('product_tmpl_id', '=', product.id),
            ('is_ai_price', '=', True),
        ], limit=1)

        if existing_ai_line:
            existing_ai_line.sudo().write(price_vals)
        else:
            create_vals = {'pricelist_id': pricelist.id,
                           'product_tmpl_id': product.id,
                           'applied_on': '1_product',
                           'is_ai_price': True,
                           **price_vals,
                           }
            new_line = self.env['product.pricelist.item'].sudo().create(create_vals)

    # =========================================================================
    # LOGGING HELPERS
    # =========================================================================

    def _create_dp_log(self, status, message='', total_tokens=0, log_lines=None, applied=False, pricelists_updated=0):
        self.ensure_one()
        log_vals = {
            'vraja_common_log_store': 'dynamic_pricing',
            'dp_log_message': message,
            'dp_total_products': len(log_lines) if log_lines else 0,
            'dp_total_tokens': total_tokens,
            'dp_applied': applied,
            'dp_pricelists_updated': pricelists_updated,
            'status': status,
            'line_ids': [(0, 0, line) for line in (log_lines or [])],
        }
        return self.env['vraja.ai.log'].sudo().create(log_vals)

    def _build_log_line(self, product, result, status, old_price=None):
        _logger.info('DP _build_log_line result: %s', result)  # ADD TEMPORARILY

        return {
            'dp_product_id': product.id,
            'dp_product_name': product.name,
            'dp_segment_name': result.get('segment_name', ''),
            'dp_old_price': old_price or product.list_price,
            'dp_ai_suggested_price': result.get('suggested_price', 0),
            'dp_decision': result.get('decision', 'hold'),
            'dp_margin_before': result.get('margin_before', 0),
            'dp_margin_after': result.get('margin_after', 0),
            'dp_reason': result.get('reason', ''),
            'dp_status': status,
        }

    # =========================================================================
    # CRON
    # =========================================================================

    @api.model
    def action_cron_dp_run_analysis(self):
        """
        Scheduled action. Segments are not stored in Odoo in this design —
        extend this method to pass stored segments when that feature is added.
        """
        card = self.sudo().search([
            ('vraja_common_store', '=', 'dynamic_pricing'),
            ('vraja_common_card_active', '=', True),
            ('dp_auto_apply', '=', True),
        ], limit=1)

        if not card:
            return

        segments = json.loads(card.dp_segment_rules_json or '[]')
        card.action_run_dynamic_pricing(segments=segments)
        if card.dp_status == 'done':
            card.action_apply_dynamic_pricing(segments=segments)

    # =========================================================================
    # Dashboard Code
    # =========================================================================
    def action_open_dp_analysis_dashboard(self):
        """Open the rich analysis dashboard without changing the existing review flow."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'dynamic_pricing_analysis_dashboard',
            'target': 'current',
            'params': {
                'card_id': self.id,
                'store': self.vraja_common_store,
            },
        }

    @api.model
    def action_get_dp_analysis_dashboard_data(self, card_id, filters=None):
        """
        Return dynamic dashboard data for the selected date window and row limit.
        Reads live AI result JSON + live sales data each call so filters work instantly.
        """
        filters = filters or {}
        card = self.sudo().browse(card_id)
        if not card.exists() or card.vraja_common_store != 'dynamic_pricing':
            return {}

        date_from, date_to = self._dp_get_analysis_dates(filters)
        limit = int(filters.get('limit') or 5)
        limit = limit if limit in (5, 10, 15) else 5

        # Parse AI result JSON — it's a flat LIST of product×segment dicts
        ai_rows = card._dp_parse_analysis_results()

        # All unique product IDs from AI results
        selected_products = card.dp_selected_product_ids.sudo()
        selected_ids = selected_products.ids or list({r['product_id'] for r in ai_rows if r.get('product_id')})

        # Sales data keyed by product template ID
        sales_by_product = card._dp_get_sales_by_product(selected_ids, date_from, date_to)

        # Build enriched rows — one per product×segment
        enriched_rows = []
        for row in ai_rows:
            pid = row.get('product_id')
            if not pid:
                continue
            sales = sales_by_product.get(int(pid), {})
            current_price = float(row.get('current_price') or 0.0)
            suggested_price = float(row.get('suggested_price') or 0.0)
            delta = suggested_price - current_price if suggested_price else 0.0
            delta_pct = (delta / current_price * 100.0) if current_price else 0.0

            enriched_rows.append({
                'product_id': pid,
                'product_name': row.get('product_name', ''),
                'segment_name': row.get('segment_name', ''),
                'qty_sold': round(sales.get('qty_sold', 0.0), 2),
                'revenue': round(sales.get('revenue', 0.0), 2),
                'current_price': round(current_price, 2),
                'suggested_price': round(suggested_price, 2),
                'price_delta': round(delta, 2),
                'price_delta_pct': round(delta_pct, 2),
                'decision': row.get('decision') or 'not_analyzed',
                'margin_before': round(float(row.get('margin_before') or 0.0), 2),
                'margin_after': round(float(row.get('margin_after') or 0.0), 2),
                'reason': row.get('reason') or '',
            })

        # Sort by revenue + price delta for ranking
        enriched_rows.sort(
            key=lambda r: (r['revenue'], abs(r['price_delta_pct']), r['qty_sold']),
            reverse=True
        )
        top_rows = enriched_rows[:limit]

        # Build segment breakdown
        segment_data = card._dp_build_segment_data(enriched_rows)

        # Build at-risk products (low margin after AI)
        at_risk = sorted(
            [r for r in enriched_rows if 0 < r['margin_after'] < 15],
            key=lambda r: r['margin_after']
        )[:5]

        # Build top margin improvers
        top_improvers = sorted(
            [r for r in enriched_rows if r['margin_after'] > r['margin_before']],
            key=lambda r: r['margin_after'] - r['margin_before'],
            reverse=True
        )[:5]

        summary = card._dp_build_analysis_summary(enriched_rows, top_rows, ai_rows)

        return {
            'card': {
                'id': card.id,
                'name': card.vraja_common_card_name,
                'status': card.dp_status,
                'analyzed_on': str(card.dp_analyzed_on) if card.dp_analyzed_on else '',
            },
            'currency': self.env.company.currency_id.name or 'USD',
            'filters': {
                'period': filters.get('period') or 'last_7_days',
                'limit': limit,
                'date_from': str(date_from),
                'date_to': str(date_to),
            },
            'summary': summary,
            'top_products': top_rows,
            'decision_mix': card._dp_get_decision_mix(enriched_rows),
            'segment_data': segment_data,
            'at_risk': at_risk,
            'top_improvers': top_improvers,
        }

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _dp_get_analysis_dates(self, filters):
        today = fields.Date.context_today(self)
        period = filters.get('period') or 'last_7_days'
        if period == 'custom':
            date_from = fields.Date.to_date(filters.get('date_from')) if filters.get('date_from') else today
            date_to = fields.Date.to_date(filters.get('date_to')) if filters.get('date_to') else today
            return (date_from, date_to) if date_from <= date_to else (date_to, date_from)
        days = 30 if period == 'last_30_days' else 7
        return fields.Date.subtract(today, days=days - 1), today

    def _dp_parse_analysis_results(self):
        """
        Parse stored AI JSON — dp_result_json is a flat LIST of dicts,
        one per product × segment pair.
        """
        self.ensure_one()
        if not self.dp_result_json:
            return []
        try:
            parsed = json.loads(self.dp_result_json)
            if isinstance(parsed, list):
                return parsed
            # Legacy: if somehow a dict was stored, convert to list
            if isinstance(parsed, dict):
                return list(parsed.values())
            return []
        except (json.JSONDecodeError, TypeError):
            return []

    def _dp_get_sales_by_product(self, product_tmpl_ids, date_from, date_to):
        if not product_tmpl_ids:
            return {}
        start_dt = datetime.combine(date_from, time.min)
        end_dt = datetime.combine(date_to, time.max)
        lines = self.env['sale.order.line'].sudo().search([
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', fields.Datetime.to_string(start_dt)),
            ('order_id.date_order', '<=', fields.Datetime.to_string(end_dt)),
            ('product_id.product_tmpl_id', 'in', product_tmpl_ids),
        ])
        sales = {}
        for line in lines:
            tmpl_id = line.product_id.product_tmpl_id.id
            bucket = sales.setdefault(tmpl_id, {'qty_sold': 0.0, 'revenue': 0.0})
            bucket['qty_sold'] += line.product_uom_qty
            bucket['revenue'] += line.price_total
        return sales

    def _dp_build_analysis_summary(self, rows, top_rows, ai_rows):
        decisions = [r['decision'] for r in rows]
        actionable = [r for r in rows if r['decision'] in ('increase', 'decrease')]
        margin_lifts = [
            r['margin_after'] - r['margin_before']
            for r in rows if r['margin_before'] or r['margin_after']
        ]
        price_changes = [r['price_delta_pct'] for r in actionable]
        unique_products = len(set(r['product_id'] for r in rows))
        unique_segments = len(set(r['segment_name'] for r in rows if r.get('segment_name')))

        return {
            'total_products': unique_products,
            'total_segments': unique_segments,
            'analyzed_products': len(ai_rows),
            'top_products': len(top_rows),
            'total_revenue': round(sum(r['revenue'] for r in rows), 2),
            'total_qty_sold': round(sum(r['qty_sold'] for r in rows), 2),
            'avg_margin_lift': round(sum(margin_lifts) / len(margin_lifts), 2) if margin_lifts else 0.0,
            'avg_price_change': round(sum(price_changes) / len(price_changes), 2) if price_changes else 0.0,
            'increase_count': decisions.count('increase'),
            'decrease_count': decisions.count('decrease'),
            'hold_count': decisions.count('hold'),
            'skip_count': decisions.count('skip'),
        }

    def _dp_build_segment_data(self, rows):
        """Build per-segment summary for the segment performance table."""
        segments = defaultdict(lambda: {
            'products': 0, 'increase': 0, 'decrease': 0,
            'hold': 0, 'skip': 0,
            'margin_before_sum': 0.0, 'margin_after_sum': 0.0,
            'revenue': 0.0,
        })
        for row in rows:
            seg = row.get('segment_name') or 'Unknown'
            s = segments[seg]
            s['products'] += 1
            decision = row.get('decision', '')
            if decision in s:
                s[decision] += 1
            s['margin_before_sum'] += row.get('margin_before', 0.0)
            s['margin_after_sum'] += row.get('margin_after', 0.0)
            s['revenue'] += row.get('revenue', 0.0)

        result = []
        for seg_name, s in segments.items():
            count = s['products'] or 1
            result.append({
                'segment_name': seg_name,
                'products': s['products'],
                'increase': s['increase'],
                'decrease': s['decrease'],
                'hold': s['hold'],
                'skip': s['skip'],
                'avg_margin_before': round(s['margin_before_sum'] / count, 2),
                'avg_margin_after': round(s['margin_after_sum'] / count, 2),
                'margin_improvement': round(
                    (s['margin_after_sum'] - s['margin_before_sum']) / count, 2
                ),
                'revenue': round(s['revenue'], 2),
            })
        return sorted(result, key=lambda x: x['revenue'], reverse=True)

    def _dp_get_decision_mix(self, rows):
        total = len(rows) or 1
        colors = {
            'increase': '#21dc96',
            'decrease': '#ff336d',
            'hold': '#ffae4a',
            'skip': '#8b95b7',
            'not_analyzed': '#6f7f99',
        }
        labels = {
            'increase': 'Increase',
            'decrease': 'Decrease',
            'hold': 'Hold',
            'skip': 'Skip',
            'not_analyzed': 'Not Analysed',
        }
        return [
            {
                'key': key,
                'label': labels[key],
                'count': sum(1 for r in rows if r['decision'] == key),
                'percent': round(sum(1 for r in rows if r['decision'] == key) / total * 100, 2),
                'color': colors[key],
            }
            for key in ('increase', 'decrease', 'hold', 'skip', 'not_analyzed')
        ]
