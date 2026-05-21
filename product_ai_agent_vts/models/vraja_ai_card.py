from odoo import models, api, fields
import json
import os
import requests
import logging
import base64
import tempfile
import xlsxwriter
from odoo.exceptions import UserError
from io import BytesIO

_logger = logging.getLogger(__name__)


class VrajaAICard(models.Model):
    _inherit = 'vraja.ai.card'

    # Many2many
    product_ai_selected_product_ids = fields.Many2many(
        'product.template', 'vraja_card_product_rel', 'card_id', 'product_id',
        string='Selected Products', store=True, domain=[('active', '=', True), ('sale_ok', '=', True)], )
    product_ai_excel_attachment_id = fields.Many2one(
        'ir.attachment', string='Selected Products Excel', readonly=True,
    )

    # Float
    product_ai_price_tolerance = fields.Float(string='Price Tolerance (%)', default=15.0)

    # Integer
    product_ai_max_suggestions = fields.Integer(string='Max Suggestions per Product', default=5)
    product_ai_sales_history_days = fields.Integer(string='Sales History Days', default=30,
                                                   help='Number of days of sales history to include in AI analysis.', )

    # Boolean
    product_ai_use_category = fields.Boolean(default=True, string='Use Category')
    product_ai_use_tags = fields.Boolean(default=True, string='Use Tags')
    product_ai_use_price = fields.Boolean(default=True, string='Use Price')
    product_ai_use_attributes = fields.Boolean(default=True, string='Use Attributes')
    product_ai_use_sales_history = fields.Boolean(default=True, string='Use Sales History')
    product_ai_auto_apply = fields.Boolean(string='Auto Apply Results',default=False,help='If enabled, AI results will be automatically applied to products after analysis.')

    # Text
    product_ai_instruction = fields.Text(string='AI Instruction',default=lambda self: self._default_product_ai_instruction(), )
    product_ai_default_prompt = fields.Text(string='AI Prompt',default=lambda self: self._default_product_ai_prompt(), )
    product_ai_business_info = fields.Text(string='Business Info',help='Describe your business context to help AI make better suggestions.', )
    product_ai_raw_result = fields.Text(string='AI Raw Result', readonly=True)
    product_ai_result_json = fields.Text(string='AI Result JSON', readonly=True)
    product_ai_error = fields.Text(string='AI Error', readonly=True)

    # Datetime
    product_ai_analyzed_on = fields.Date(string='AI Analyzed On', readonly=True)

    # Selection
    vraja_common_store = fields.Selection(selection_add=[('product_alt_acc', 'Product Alternate and Accessory')])
    product_ai_min_confidence = fields.Selection([
        ('all', 'All (high + medium + low)'),
        ('medium', 'High & medium only'),
        ('high', 'High only'),
    ], default='all', string='Minimum Confidence')

    product_ai_suggestion_type = fields.Selection([
        ('both', 'Both alternatives and accessories'),
        ('alternatives', 'Alternatives only'),
        ('accessories', 'Accessories only'),
    ], default='both', string='Suggestion Type')

    product_ai_status = fields.Selection([
        ('idle', 'Idle'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], default='idle', string='AI Status')

    # ══════════════════════════════════════════════════════════════════════════
    # Default prompts
    # ══════════════════════════════════════════════════════════════════════════

    @api.model
    def _default_product_ai_instruction(self):
        return """
    You are a product catalog analyst. Analyse the Excel file and return alternatives and accessories for each product in Sheet 1.

    SHEETS:
    - Sheet 1: Target products (need alternatives and accessories assigned). Columns: Product ID, Product Name, Price, Category.
    - Sheet 2: Full catalog to pick suggestions FROM. Columns: Product ID, Product Name, Price, Category.
    - Sheet 3: Sales co-purchase history (if present). Use as accessory signal.

    ALTERNATIVE RULES:
    - Same category as main product
    - Price difference must be within the configured tolerance percentage
    - Must serve the same purpose as the main product
    - Can include products from Sheet 1 as alternatives for each other
    - Never suggest the product itself (same Product ID = skip)

    ACCESSORY RULES:
    - Accessory price MUST be strictly less than the main product price — no exceptions
    - Must complement or enhance the main product
    - Can come from any category — not restricted to same category
    - Sales history co-purchase is the strongest signal — if two products are bought together, suggest as accessory
    - If no sales history, use price and category logic to find complementary products
    - Never suggest the product itself (same Product ID = skip)
    - Never suggest a product with price >= main product price as accessory

    HARD CONSTRAINTS — NEVER VIOLATE:
    1. Only use Product IDs and Product Names that exist exactly in Sheet 2
    2. Never invent or modify Product IDs or Names
    3. Every product in Sheet 1 must appear in output — use empty array if no match
    4. Accessory price < main product price — this is absolute, no exceptions
    5. Return valid JSON only — no markdown, no text outside JSON array
        """.strip()

    @api.model
    def _default_product_ai_prompt(self):
        return """
    For each product in Sheet 1, find the best alternatives and accessories from Sheet 2.

    STEP 1 — ALTERNATIVES:
    Look in Sheet 2 for products that:
    - Have the same Category as the main product
    - Have a price within the configured tolerance band
    - Serve the same purpose
    - Are not the same product (different Product ID)

    STEP 2 — ACCESSORIES:
    Look in Sheet 2 for products that:
    - First check Sheet 3 sales history — products bought together = accessory
    - Have a price STRICTLY LESS than the main product price
    - Are from a different category than the main product
    - Are not the same product (different Product ID)

    STEP 3 — VALIDATE before adding any suggestion:
    - Is Product ID different from main product ID? If same → remove
    - For accessories: is price < main product price? If not → remove
    - Does product exist in Sheet 2? If not → remove

    OUTPUT FORMAT (JSON array only, no other text):
    [
        {
            "product_id": <integer ID from Sheet 1>,
            "product_name": "<name from Sheet 1>",
            "alternatives": [
                {"product_id": <integer ID from Sheet 2>, "product_name": "<name from Sheet 2>"}
            ],
            "accessories": [
                {"product_id": <integer ID from Sheet 2>, "product_name": "<name from Sheet 2>"}
            ]
        }
    ]
        """.strip()

    # ══════════════════════════════════════════════════════════════════════════
    # Card creation
    # ══════════════════════════════════════════════════════════════════════════

    @api.model
    def _create_find_product_record(self):
        record = self.search([('vraja_common_store', '=', 'product_alt_acc')], limit=1)
        if not record:
            record = self.create({
                'vraja_common_card_name': 'Product Alternate & Accessory',
                'vraja_common_card_description': 'AI suggests alternatives and accessories for your products.',
                'vraja_common_card_active': True,
                'vraja_common_store': 'product_alt_acc',
                'product_ai_instruction': self._default_product_ai_instruction(),
                'product_ai_default_prompt': self._default_product_ai_prompt(),
            })
        return record

    # ══════════════════════════════════════════════════════════════════════════
    # Prompt builder — config only, data is in the Excel file
    # ══════════════════════════════════════════════════════════════════════════

    def _build_product_ai_prompt(self):
        """Builds the user prompt with configuration context only.
        Product data is already in the Excel file sent as attachment.
        """
        self.ensure_one()

        sales_note = (
            f'Sheet 3 (Sales History) IS present — last '
            f'{self.product_ai_sales_history_days or 30} days.'
            if self.product_ai_use_sales_history else
            'Sheet 3 (Sales History) is NOT present.'
        )

        return (
            f"{self.product_ai_default_prompt}\n\n"
            f"Configuration:\n"
            f"- Suggestion type: {self.product_ai_suggestion_type}\n"
            f"- Price tolerance: {self.product_ai_price_tolerance}%\n"
            f"- Max suggestions per product: {self.product_ai_max_suggestions}\n"
            f"- Business context: {self.product_ai_business_info or 'None'}\n"
            f"- {sales_note}"
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Excel generation — Sheet 1, 2, 3
    # ══════════════════════════════════════════════════════════════════════════

    def _generate_selected_products_excel(self):
        """Generates Excel with Sheet 1 (selected), Sheet 2 (catalog),
        Sheet 3 (sales history if enabled). Saves as ir.attachment.
        """
        self.ensure_one()

        if not self.product_ai_selected_product_ids:
            self.product_ai_excel_attachment_id = False
            return False

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)

        header_fmt = workbook.add_format({
            'bold': True, 'bg_color': '#4472C4',
            'font_color': '#FFFFFF', 'border': 1,
        })
        cell_fmt = workbook.add_format({'border': 1, 'text_wrap': True})

        # Dynamic columns based on enabled rules
        columns = ['Product ID', 'Product Name', 'Price', 'Category']
        if self.product_ai_use_tags:
            columns.append('Tags')
        if self.product_ai_use_attributes:
            columns.append('Attributes')

        def get_row(product):
            row = [
                product.id,
                product.name,
                product.list_price,
                product.categ_id.complete_name or '',
            ]
            if self.product_ai_use_tags:
                tags = [t.name for t in product.product_tag_ids]
                row.append(', '.join(tags))
            if self.product_ai_use_attributes:
                attrs_parts = []
                for line in product.attribute_line_ids:
                    values = ', '.join(v.name for v in line.value_ids)
                    attrs_parts.append(f"{line.attribute_id.name}: {values}")
                row.append(' | '.join(attrs_parts))
            return row

        def write_sheet(sheet, products):
            for col, header in enumerate(
                    columns):  # enumerate(columns) gives you both the index and the value at the same time while looping.
                sheet.write(0, col, header, header_fmt)
                sheet.set_column(col, col, 20)
            for row_idx, product in enumerate(products, start=1):
                for col_idx, value in enumerate(get_row(product)):
                    sheet.write(row_idx, col_idx, value, cell_fmt)

        # Sheet 1 — Selected Products
        sheet1 = workbook.add_worksheet('Selected Products')
        write_sheet(sheet1, self.product_ai_selected_product_ids)

        # Sheet 2 — Full Catalog
        all_products = self.env['product.template'].search([
            ('active', '=', True), ('sale_ok', '=', True),
        ])
        sheet2 = workbook.add_worksheet('Full Catalog')
        write_sheet(sheet2, all_products)

        # Sheet 3 — Sales History (only if enabled)
        if self.product_ai_use_sales_history:
            days = self.product_ai_sales_history_days or 30
            date_from = fields.Datetime.now() - __import__('datetime').timedelta(days=days)

            sheet3 = workbook.add_worksheet(f'Sales History ({days} days)')
            history_headers = [
                'Product Name', 'Total Orders', 'Total Qty Sold',
                'Frequently Bought With (Product Name)', 'Co-purchase Count',
            ]
            for col, header in enumerate(history_headers):
                sheet3.write(0, col, header, header_fmt)
                sheet3.set_column(col, col, 25)

            row_idx = 1
            for product in self.product_ai_selected_product_ids:
                product_variants = product.product_variant_ids.ids
                lines = self.env['sale.order.line'].search([
                    ('order_id.state', 'in', ['sale', 'done']),
                    ('order_id.date_order', '>=', date_from),
                    ('product_id', 'in', product_variants),
                ])

                order_ids = lines.mapped('order_id').ids
                total_qty = sum(lines.mapped('product_uom_qty'))

                co_lines = self.env['sale.order.line'].search([
                    ('order_id', 'in', order_ids),
                    ('product_id', 'not in', product_variants),
                ])

                co_count = {}
                for line in co_lines:
                    tmpl = line.product_id.product_tmpl_id
                    if tmpl.id not in co_count:
                        co_count[tmpl.id] = {'name': tmpl.name, 'count': 0}
                    co_count[tmpl.id]['count'] += 1

                sorted_co = sorted(co_count.items(), key=lambda x: x[1]['count'], reverse=True)[:10]

                for co_id, co_data in sorted_co:
                    sheet3.write(row_idx, 0, product.name, cell_fmt)
                    sheet3.write(row_idx, 1, len(order_ids), cell_fmt)
                    sheet3.write(row_idx, 2, total_qty, cell_fmt)
                    sheet3.write(row_idx, 3, co_data['name'], cell_fmt)
                    sheet3.write(row_idx, 4, co_data['count'], cell_fmt)
                    row_idx += 1

        workbook.close()
        output.seek(0)
        file_data = base64.b64encode(output.read())

        if self.product_ai_excel_attachment_id:
            self.product_ai_excel_attachment_id.sudo().unlink()

        attachment = self.env['ir.attachment'].create({
            'name': f'product_ai_data_{self.id}.xlsx',
            'type': 'binary',
            'datas': file_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self.id,
        })
        self.product_ai_excel_attachment_id = attachment.id
        return attachment

    # ══════════════════════════════════════════════════════════════════════════
    # OpenAI API — upload Excel + call Responses API
    # ══════════════════════════════════════════════════════════════════════════

    def _upload_excel_to_openai(self, attachment):
        """Uploads Excel attachment to OpenAI Files API and returns file_id."""
        api_key = self.env['vraja.ai.config'].sudo().search([('id', '=', 1)],
                                                            limit=1).openai_api_key  # self.vraja_ai_configration_id.openai_api_key

        file_bytes = base64.b64decode(attachment.datas)

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(file_bytes)
            temp_path = f.name
        result = {}

        try:
            boundary = "----WebKitFormBoundary123456"
            with open(temp_path, "rb") as file:
                file_data = file.read()

            body = (
                       f"--{boundary}\r\n"
                       'Content-Disposition: form-data; name="purpose"\r\n\r\n'
                       'assistants\r\n'
                       f"--{boundary}\r\n"
                       f'Content-Disposition: form-data; name="file"; filename="{attachment.name}"\r\n'
                       'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n'
                   ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

            header = {"Authorization": f"Bearer {api_key}",
                      "Content-Type": f"multipart/form-data; boundary={boundary}", }

            try:
                response = requests.post("https://api.openai.com/v1/files", data=body, headers=header, timeout=120)
                result = response.json()

            except requests.exceptions.HTTPError as e:
                raise UserError(f"File upload failed HTTP: {str(e)}")

        finally:
            try:
                os.unlink(temp_path)
            except Exception as e:
                _logger.info("OpenAI Error: %s", e)

        file_id = result.get('id') if result else False
        if not file_id:
            error_msg = result.get('error', {}).get('message')
            raise UserError(f'File upload failed: {error_msg}')
        return file_id

    def _call_product_ai_api(self, system_prompt, user_prompt):
        """Upload Excel and call OpenAI Responses API."""

        api_key = self.env['vraja.ai.config'].sudo().search([('id', '=', 1)], limit=1).openai_api_key
        if not api_key:
            raise UserError('OpenAI API key is not configured.')

        if not self.product_ai_excel_attachment_id:
            raise UserError('No data file found. Please save settings first.')

        file_id = self._upload_excel_to_openai(self.product_ai_excel_attachment_id)

        try:
            payload = {
                "model": "gpt-4o",
                "input": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": user_prompt},
                            {"type": "input_file", "file_id": file_id},
                        ]
                    }
                ]
            }

            response = requests.post("https://api.openai.com/v1/responses", json=payload,
                                     headers={"Authorization": f"Bearer {api_key}",
                                              "Content-Type": "application/json", },
                                     timeout=120)

            response.raise_for_status()
            body = response.json()
            _logger.info("OpenAI usage: %s", body.get("usage"))

            return body["output"][0]["content"][0]["text"]

        except requests.exceptions.RequestException as e:
            raise UserError(f"OpenAI API Error: {str(e)}")

        except (KeyError, IndexError, TypeError):
            raise UserError(f"Unexpected response format: {body}")

        finally:
            try:
                requests.delete(f"https://api.openai.com/v1/files/{file_id}",
                                headers={"Authorization": f"Bearer {api_key}"},
                                timeout=10)
            except Exception as e:
                _logger.info("OpenAI Error: %s", e)

    def _parse_product_ai_response(self, raw_text):
        """Parses AI JSON response into a dict keyed by product_id.
        No Sheet 4 writing — results go directly to product_ai_result_json
        and are shown in the Step 6 table.
        """
        text = raw_text.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[-1]
            if text.endswith('```'):
                text = text.rsplit('```', 1)[0]

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise UserError(f'AI response was not valid JSON: {e}')

        if not isinstance(data, list):
            raise UserError(f'Expected JSON array from AI, got: {type(data).__name__}')

        result = {}
        for item in data:
            pid = item.get('product_id')
            if pid:
                result[int(pid)] = {
                    'product_name': item.get('product_name', ''),
                    'alternatives': item.get('alternatives', []),
                    'accessories': item.get('accessories', []),
                }
        return result

    # ══════════════════════════════════════════════════════════════════════════
    # Methods called from JS dashboard
    # ══════════════════════════════════════════════════════════════════════════

    def action_run_product_ai(self):
        """Called from Run AI button — uploads Excel, calls AI, stores JSON result."""
        self.ensure_one()

        if not self.product_ai_selected_product_ids:
            raise UserError('Please select at least one product before running AI.')

        if not self.product_ai_excel_attachment_id:
            raise UserError('No data file found. Please save settings first to generate the Excel file.')

        self.write({'product_ai_status': 'running', 'product_ai_error': False})

        try:
            system_prompt = self.product_ai_instruction or ''
            user_prompt = self._build_product_ai_prompt()

            raw_response = self._call_product_ai_api(system_prompt, user_prompt)
            parsed = self._parse_product_ai_response(raw_response)

            self.write({
                'product_ai_raw_result': raw_response,
                'product_ai_result_json': json.dumps(parsed, ensure_ascii=False, indent=2),
                'product_ai_status': 'done',
                'product_ai_analyzed_on': fields.Datetime.now(),
            })

        except UserError as e:
            self.write({'product_ai_status': 'error', 'product_ai_error': str(e)})
            raise UserError(e)

        return True

    def action_apply_product_ai_suggestions(self):
        """Called from Apply button — writes alternatives/accessories to Odoo products."""
        self.ensure_one()
        if not self.product_ai_result_json:
            raise UserError('No AI results to apply. Please run AI first.')

        parsed = json.loads(self.product_ai_result_json)
        PT = self.env['product.template']

        applied = 0
        for pid_str, result in parsed.items():
            pid = int(pid_str)
            product = PT.browse(pid)
            if not product.exists():
                _logger.warning(f'Product ID {pid} not found — skipping')
                continue

            alts = result.get('alternatives', [])
            accs = result.get('accessories', [])

            alt_ids = [int(r['product_id']) for r in alts if 'product_id' in r]
            acc_ids = [int(r['product_id']) for r in accs if 'product_id' in r]

            valid_alts = PT.browse(alt_ids).filtered('active')
            valid_accs = PT.browse(acc_ids).filtered('active')

            write_vals = {}
            if self.product_ai_suggestion_type in ('both', 'alternatives'):
                write_vals['alternative_product_ids'] = [(6, 0, valid_alts.ids)]
            if self.product_ai_suggestion_type in ('both', 'accessories'):
                write_vals['accessory_product_ids'] = [(6, 0, valid_accs.product_variant_ids.ids)]

            if write_vals:
                product.write(write_vals)
                applied += 1
                _logger.info(f'Applied to {product.name} — alts: {valid_alts.ids} accs: {valid_accs.ids}')

        return {'applied': applied}

    def action_get_product_ai_dashboard_data(self):
        """Called from JS to load current card state for the dashboard."""
        self.ensure_one()
        return {
            'card_id': self.id,
            'card_name': self.vraja_common_card_name,
            'product_ai_business_info': self.product_ai_business_info or '',
            'product_ai_suggestion_type': self.product_ai_suggestion_type,
            'product_ai_price_tolerance': self.product_ai_price_tolerance,
            'product_ai_max_suggestions': self.product_ai_max_suggestions,
            'product_ai_min_confidence': self.product_ai_min_confidence,
            'product_ai_use_category': self.product_ai_use_category,
            'product_ai_use_tags': self.product_ai_use_tags,
            'product_ai_use_price': self.product_ai_use_price,
            'product_ai_use_attributes': self.product_ai_use_attributes,
            'product_ai_use_sales_history': self.product_ai_use_sales_history,
            'product_ai_sales_history_days': self.product_ai_sales_history_days,
            'product_ai_status': self.product_ai_status,
            'product_ai_error': self.product_ai_error or '',
            'product_ai_analyzed_on': str(self.product_ai_analyzed_on) if self.product_ai_analyzed_on else '',
            'product_ai_result_json': self.product_ai_result_json or '',
            'product_ai_auto_apply': self.product_ai_auto_apply,
            'selected_products': [
                {'id': p.id, 'name': p.name, 'price': p.list_price}
                for p in self.product_ai_selected_product_ids
            ],
            'excel_attachment': {
                'id': self.product_ai_excel_attachment_id.id,
                'name': self.product_ai_excel_attachment_id.name,
                'url': f'/web/content/{self.product_ai_excel_attachment_id.id}?download=true',
            } if self.product_ai_excel_attachment_id else False,
        }

    def action_save_product_ai_dashboard_data(self, values):
        """Called from JS to save form values from dashboard."""
        self.ensure_one()
        allowed_fields = [
            'product_ai_business_info',
            'product_ai_suggestion_type',
            'product_ai_price_tolerance',
            'product_ai_max_suggestions',
            'product_ai_min_confidence',
            'product_ai_use_category',
            'product_ai_use_tags',
            'product_ai_use_price',
            'product_ai_use_attributes',
            'product_ai_use_sales_history',
            'product_ai_sales_history_days',
            'product_ai_auto_apply',
        ]
        write_vals = {k: v for k, v in values.items() if k in allowed_fields}

        if 'product_ai_selected_product_ids' in values:
            write_vals['product_ai_selected_product_ids'] = [
                (6, 0, values['product_ai_selected_product_ids'])
            ]

        self.write(write_vals)

        if 'product_ai_selected_product_ids' in values:
            self.invalidate_recordset()
            self._generate_selected_products_excel()

        return {'success': True}


# =================================================================================================================
#                                             CRON SECTION
# =================================================================================================================

    @api.model
    def action_cron_product_ai_generate_excel(self):
        """Cron job — Auto regenerates Excel for all active product AI cards."""
        card = self.search([
            ('vraja_common_store', '=', 'product_alt_acc'),
            ('vraja_common_card_active', '=', True),
            ('product_ai_selected_product_ids', '!=', False),
        ],limit=1)

        if card:
            card._generate_selected_products_excel()
            _logger.info(f'Auto Excel generated for card: {card.vraja_common_card_name}')


    @api.model
    def action_cron_product_ai(self):
        """Cron job — Auto generates Excel, runs AI analysis and applies results if enabled."""
        card = self.search([
            ('vraja_common_store', '=', 'product_alt_acc'),
            ('vraja_common_card_active', '=', True),
            ('product_ai_selected_product_ids', '!=', False),
        ], limit=1)
        if not card:
            return

        if card.product_ai_excel_attachment_id and card.product_ai_auto_apply:
            card.action_run_product_ai()
            _logger.info(f'Auto AI analysis completed for card: {card.vraja_common_card_name}')

        if card.product_ai_status == 'done':
           card.action_apply_product_ai_suggestions()
           _logger.info(f'Auto apply completed for card: {card.vraja_common_card_name}')


