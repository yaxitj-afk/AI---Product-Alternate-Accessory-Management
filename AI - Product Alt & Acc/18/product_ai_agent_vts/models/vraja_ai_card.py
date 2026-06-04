# -*- coding: utf-8 *-*
from odoo import models, api, fields
import json
import os
import requests
import logging
import base64
import tempfile
import xlsxwriter
import datetime
import openpyxl
from odoo.exceptions import UserError
from io import BytesIO

_logger = logging.getLogger(__name__)


class VrajaAICard(models.Model):
    _inherit = 'vraja.ai.card'

    # Many2many
    product_ai_selected_product_ids = fields.Many2many(
        'product.template', 'vraja_card_product_rel', 'card_id', 'product_id',
        string='Selected Products', store=True, domain=[('active', '=', True), ('sale_ok', '=', True)])
    product_ai_excel_attachment_id = fields.Many2one(
        'ir.attachment', string='Selected Products Excel', readonly=True, )

    # Float
    product_ai_price_tolerance = fields.Float(string='Price Tolerance (%)', default=15.0)

    # Integer
    product_ai_max_suggestions = fields.Integer(string='Max Suggestions per Product', default=5)
    product_ai_sales_history_days = fields.Integer(string='Sales History Days', default=30,
                                                   help='Number of days of sales history to include in AI analysis.', )
    product_ai_last_tokens = fields.Integer(string='Last Run Tokens', default=0)

    # Boolean
    product_ai_use_category = fields.Boolean(default=True, string='Use Category')
    product_ai_use_tags = fields.Boolean(default=True, string='Use Tags')
    product_ai_use_price = fields.Boolean(default=True, string='Use Price')
    product_ai_use_attributes = fields.Boolean(default=True, string='Use Attributes')
    product_ai_use_sales_history = fields.Boolean(default=True, string='Use Sales History')
    product_ai_auto_apply = fields.Boolean(string='Auto Apply Results', default=False,
                                           help='If enabled, AI results will be automatically applied to products after analysis.')

    # Text
    product_ai_instruction = fields.Text(string='AI Instruction',
                                         default=lambda self: self._default_product_ai_instruction(), )
    product_ai_default_prompt = fields.Text(string='AI Prompt',
                                            default=lambda self: self._default_product_ai_prompt(), )
    product_ai_business_info = fields.Text(string='Business Info',
                                           help='Describe your business context to help AI make better suggestions.', )
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
    ], default='high', string='Minimum Confidence')

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

    def action_log_view(self):
        action = super().action_log_view()
        if self.vraja_common_store == 'product_alt_acc':
            action['name'] = 'Product AI Logs'
            action['target'] = 'main'
            action['views'] = [(False, 'list'),
                               (self.env.ref('product_ai_agent_vts.product_ai_log_form_vts').id, 'form'), ]
            action['context'] = {'search_default_filter_product_ai': 1, 'create': False, }
        return action

    # ══════════════════════════════════════════════════════════════════════════
    # Default prompts
    # ══════════════════════════════════════════════════════════════════════════

    def action_review_dashboard(self):
        action = super().action_review_dashboard()
        self.ensure_one()
        if self.vraja_common_store == 'product_alt_acc':
            action['tag'] = 'product_ai_agent_dashboard_template'
        return action

    @api.model
    def action_product_ai_get_default_card_id(self):
        """Return the product AI card id so the dashboard can recover after refresh."""
        card = self.sudo().search([('vraja_common_store', '=', 'product_alt_acc')], limit=1)
        return card.id if card else False

    @api.model
    def _default_product_ai_instruction(self):
        return """
        You are a product catalog analyst for an Odoo ERP system.

        HARD RULES — NEVER VIOLATE:
        1. Only use Product IDs and Names that exist exactly in Sheet 2
        2. Never suggest a product as its own alternative or accessory
        3. Accessory price MUST be strictly less than main product price — no exceptions
        4. Every product in Sheet 1 must appear in output — empty array if no match
        5. Return valid JSON only — no markdown, no text outside JSON
        6. Suggest only what there are asking for, if there are asking for both alternate and accessories than give both else as per the requirement.
            """.strip()

    @api.model
    def _default_product_ai_prompt(self):
        return """
        Analyse the attached Excel file. For each product in Sheet 1, find the best alternatives and accessories from Sheet 2.

        SHEET GUIDE:
        - Sheet 1 = Products that need alternatives and accessories
        - Sheet 2 = Full product catalog — pick ALL suggestions from here only
        - Sheet 3 = Sales history — shows which products customers bought together (use as strongest accessory signal)

        STEP 1 — FIND ALTERNATIVES
        An alternative is a product a customer would buy INSTEAD of the main product.

        Logic to identify alternatives:
        1. Same Category — alternative must be in the same or closely related category
        2. Same Purpose — ask yourself: "Would a customer consider this as a replacement?", Customer can realistically buy it instead of the original product
        3. Similar Price — price difference must be within the configured tolerance %
           Formula: abs(alternative_price - main_price) / main_price <= tolerance/100
        4. Different Product — alternative Product ID must NOT equal main product Product ID
        5. Similar use case, Same product type 

        STEP 2 — FIND ACCESSORIES
        An accessory is a product a customer would buy TOGETHER WITH the main product.

        Logic to identify accessories:
        1. Check Sheet 3 first — if two products appear together in sales history, they are almost certainly accessories
           Higher co-purchase count = stronger accessory signal, Is commonly purchased together
        2. Price must be STRICTLY LESS than main product price — no exceptions
           If accessory_price >= main_price → skip it, it cannot be an accessory
        3. Enhances, supports, or complements the main product
        4. Different category from main product — accessories typically come from a related but different category
        5. Complementary purpose — ask yourself: "Does this product enhance or complete the main product?"
        6. Different Product — accessory Product ID must NOT equal main product Product ID

        STEP 3 — VALIDATE EVERY SUGGESTION
        Before adding any suggestion, verify:
        ✓ Do not use keyword similarity alone for matching
        ✓ Product ID exists in Sheet 2
        ✓ Product ID is different from main product ID
        ✓ Product type and customer buying intent must match
        ✓ If relationship confidence is weak, do not return the suggestion
        ✓ For accessories: suggested price < main product price
        ✓ For alternatives: price within tolerance band

        OUTPUT FORMAT (JSON array only, no other text):
        [
            {
                "product_id": <exact integer ID from Sheet 1>,
                "product_name": "<exact name from Sheet 1>",
                "alternatives": [
                    {"product_id": <exact integer ID from Sheet 2>, "product_name": "<exact name from Sheet 2>"}
                ],
                "accessories": [
                    {"product_id": <exact integer ID from Sheet 2>, "product_name": "<exact name from Sheet 2>"}
                ]
            }
        ]
            """.strip()

    # ----------------------------------------------------------------------------------------------------------
    #                                 LOG MANAGEMENT
    # ----------------------------------------------------------------------------------------------------------

    def _create_product_ai_log(self, status, message='', total_tokens=0, log_lines=None,
                               total_alt=0, total_acc=0, applied=0):
        """Common method to create product AI logs including error/negative logs."""
        self.ensure_one()
        log_vals = {
            'vraja_common_log_store': 'product_alt_acc',
            'product_ai_suggestion_type': self.product_ai_suggestion_type,
            'product_ai_confidence': self.product_ai_min_confidence,
            'product_ai_total_products': len(log_lines) if log_lines else 0,
            'product_ai_total_alt': total_alt,
            'product_ai_total_acc': total_acc,
            'product_ai_token_used': total_tokens,
            'product_ai_log_message': message,
            'status': status,
            'line_ids': [(0, 0, line) for line in (log_lines or [])],
        }
        product_logs = self.env['vraja.ai.log'].sudo().create(log_vals)
        return product_logs

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
            self.sudo().write({'product_ai_excel_attachment_id': False})
            return False

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

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
            row = [product.id, product.name, product.list_price, product.categ_id.complete_name or '', ]
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

        if self.product_ai_use_sales_history:
            days = self.product_ai_sales_history_days or 30
            date_from = fields.Datetime.now() - datetime.timedelta(days=days)

            sheet3 = workbook.add_worksheet(f'Sales History ({days} days)')

            history_headers = ['Sale Order', 'Order Date', 'Product', 'Quantity', 'Unit Price']
            col_widths = [20, 22, 35, 12, 15]

            for col, (header, width) in enumerate(zip(history_headers, col_widths)):
                sheet3.write(0, col, header, header_fmt)
                sheet3.set_column(col, col, width)

            orders = self.env['sale.order'].search([('state', 'in', ['sale', 'done']),('date_order', '>=', date_from),
                ('order_line.product_id.product_tmpl_id', 'in', self.product_ai_selected_product_ids.ids),])

            row_idx = 1

            for order in orders.sorted(key=lambda o: o.date_order or '', reverse=True):
                order_date = order.date_order.strftime('%Y-%m-%d %H:%M:%S') if order.date_order else ''

                lines = order.order_line.filtered(lambda l: not l.is_delivery and l.price_unit >= 0 and l.product_id)

                for line in lines:
                    sheet3.write(row_idx, 0, order.name or '', cell_fmt)
                    sheet3.write(row_idx, 1, order_date, cell_fmt)
                    sheet3.write(row_idx, 2, line.product_id.display_name or '', cell_fmt)
                    sheet3.write(row_idx, 3, line.product_uom_qty or 0, cell_fmt)
                    sheet3.write(row_idx, 4, line.price_unit or 0, cell_fmt)
                    row_idx += 1

        workbook.close()
        output.seek(0)
        file_data = base64.b64encode(output.read())

        if self.product_ai_excel_attachment_id:
            self.product_ai_excel_attachment_id.sudo().unlink()

        attachment = self.env['ir.attachment'].sudo().create({
            'name': f'product_ai_data_{self.id}.xlsx',
            'type': 'binary',
            'datas': file_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self.id,
        })
        self.sudo().write({'product_ai_excel_attachment_id': attachment.id})
        return attachment

    # ══════════════════════════════════════════════════════════════════════════
    # OpenAI API — upload Excel + call Responses API
    # ══════════════════════════════════════════════════════════════════════════

    def _upload_excel_to_openai(self, attachment, api_key):
        """Uploads Excel attachment to OpenAI Files API and returns file_id."""
        file_bytes = base64.b64decode(attachment.datas)

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(file_bytes)
            temp_path = f.name

        result = {}
        try:
            boundary = "----WebKitFormBoundary123456"
            with open(temp_path, "rb") as file:
                file_data = file.read()

            body = (f"--{boundary}\r\n"
                    'Content-Disposition: form-data; name="purpose"\r\n\r\n'
                    'assistants\r\n'
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="file"; filename="{attachment.name}"\r\n'
                    'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n'
                    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

            response = requests.post(
                "https://api.openai.com/v1/files",
                data=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                timeout=120,
            )
            result = response.json()

        finally:
            try:
                os.unlink(temp_path)
            except Exception as e:
                _logger.info("Temp file cleanup error: %s", e)

        file_id = result.get('id') if result else False
        if not file_id:
            error_msg = result.get('error', {}).get('message') or 'Unknown upload error'
            raise UserError(f'{error_msg}')

        return file_id

    def _call_product_ai_api(self, system_prompt, user_prompt):
        """Upload Excel and call OpenAI Responses API."""
        config = self.env['vraja.ai.config'].sudo().search([('id', '=', 1)], limit=1)

        if not config or not config.openai_api_key:
            error_msg = 'OpenAI API key is not configured. Please set it in Configuration.'
            raise UserError(error_msg)

        if not self.product_ai_excel_attachment_id:
            error_msg = 'No data file found. Please save settings first to generate the Excel file.'
            raise UserError(error_msg)

        file_id = self._upload_excel_to_openai(self.product_ai_excel_attachment_id,config.openai_api_key,)

        try:
            payload = {
                "model": config.llm_model,
                "input": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": user_prompt},
                            {"type": "input_file", "file_id": file_id},
                        ],
                    },
                ],
            }

            response = requests.post("https://api.openai.com/v1/responses", json=payload,
                                     headers={
                                         "Authorization": f"Bearer {config.openai_api_key}",
                                         "Content-Type": "application/json",
                                     }, timeout=120, )

            response.raise_for_status()
            body = response.json()
            _logger.info("OpenAI usage: %s", body.get("usage"))
            total_tokens = body.get("usage", {}).get("total_tokens", 0)
            return body["output"][0]["content"][0]["text"], total_tokens


        except requests.exceptions.Timeout:
            error_msg = 'Request timed out. OpenAI API did not respond in time.'
            raise UserError(error_msg)

        except requests.exceptions.ConnectionError:
            error_msg = 'Connection error. Please check your internet connection.'
            raise UserError(error_msg)


        except requests.exceptions.RequestException as e:
            error_msg = f'API Request Error: {str(e)}'
            raise UserError(error_msg)


        except (KeyError, IndexError, TypeError) as e:
            error_msg = f'Unexpected response format from OpenAI: {str(e)}'
            raise UserError(error_msg)

        finally:
            try:
                requests.delete(
                    f"https://api.openai.com/v1/files/{file_id}",
                    headers={"Authorization": f"Bearer {config.openai_api_key}"},
                    timeout=10,
                )
            except Exception as e:
                _logger.info("OpenAI file cleanup error: %s", e)

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
        self.sudo().write({'product_ai_status': 'running', 'product_ai_error': False})

        try:
            system_prompt = self.product_ai_instruction or ''
            user_prompt = self._build_product_ai_prompt()
            raw_response, total_tokens = self._call_product_ai_api(system_prompt, user_prompt)
            parsed = self._parse_product_ai_response(raw_response)

            self.sudo().write({
                'product_ai_raw_result': raw_response,
                'product_ai_result_json': json.dumps(parsed, ensure_ascii=False, indent=2),
                'product_ai_status': 'done',
                'product_ai_analyzed_on': fields.Date.today(),
                'product_ai_last_tokens': total_tokens,
            })

        except UserError as e:
            error_msg = str(e)
            self.sudo().write({'product_ai_status': 'error', 'product_ai_error': error_msg})
            self._create_product_ai_log(status='failed', message=error_msg)
            self.env.cr.commit()
            raise

        return True

    def action_apply_product_ai_suggestions(self):
        """Called from Apply button — writes alternatives/accessories to Odoo products."""
        self.ensure_one()
        if not self.product_ai_result_json:
            return

        parsed = json.loads(self.product_ai_result_json)
        PT = self.env['product.template']
        log_lines = []
        total_alternatives = 0
        total_accessories = 0
        applied = 0

        for pid_str, result in parsed.items():
            pid = int(pid_str)
            product = PT.browse(pid)

            if not product.exists():
                log_lines.append({
                    'product_ai_product_id': pid,
                    'product_ai_product_name': result.get('product_name', str(pid)),
                    'product_ai_alt_applied': 0,
                    'product_ai_acc_applied': 0,
                    'product_ai_alt_names': '',
                    'product_ai_acc_names': '',
                    'product_ai_status': 'skipped',
                })
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
                product.sudo().write(write_vals)
                applied += 1

            alt_count = len(valid_alts)
            acc_count = len(valid_accs)
            total_alternatives += alt_count
            total_accessories += acc_count

            log_lines.append({
                'product_ai_product_id': product.id,
                'product_ai_product_name': product.name,
                'product_ai_alt_applied': alt_count,
                'product_ai_acc_applied': acc_count,
                'product_ai_alt_names': ', '.join(valid_alts.mapped('name')),
                'product_ai_acc_names': ', '.join(valid_accs.mapped('name')),
                'product_ai_status': 'success',
            })

        status = 'success'
        if applied == 0:
            status = 'failed'

        total_tokens = self.product_ai_last_tokens or 0
        self.sudo().write({'product_ai_status': 'idle'})

        log = self._create_product_ai_log(status=status,message=f'Applied to {applied} of {len(parsed)} products successfully.' if applied else 'No products applied.',
            log_lines=log_lines,total_alt=total_alternatives,total_acc=total_accessories,applied=applied, total_tokens=total_tokens)
        return {'applied': applied, 'log_id': log.id}

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

        self.sudo().write(write_vals)

        if 'product_ai_selected_product_ids' in values:
            self.sudo().write({'product_ai_status': 'idle'})
            self._generate_selected_products_excel()

        return {'success': True}

    # =================================================================================================================
    #                                             CRON SECTION
    # =================================================================================================================

    @api.model
    def action_cron_product_ai_generate_excel(self):
        card = self.search([
            ('vraja_common_store', '=', 'product_alt_acc'),
            ('vraja_common_card_active', '=', True),
            ('product_ai_selected_product_ids', '!=', False),
        ], limit=1)
        if card:
            card._generate_selected_products_excel()

    @api.model
    def action_cron_product_ai_run_analysis(self):
        card = self.search([
            ('vraja_common_store', '=', 'product_alt_acc'),
            ('vraja_common_card_active', '=', True),
            ('product_ai_selected_product_ids', '!=', False),
            ('product_ai_excel_attachment_id', '!=', False),
            ('product_ai_auto_apply', '=', True),
        ], limit=1)
        if not card:
            return
        card.action_run_product_ai()
        if card.product_ai_status == 'done':
            card.action_apply_product_ai_suggestions()
            card.sudo().write({'product_ai_status': 'idle'})

    # ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════
    # PRODUCT FILE UPLOAD CODE
    # ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════

    def action_import_products_from_sku_file(self, base64_data, filename):
        """Reads uploaded SKU file and returns matching product.template records."""
        self.ensure_one()
        if not isinstance(base64_data, str) or not filename:
            raise UserError('Invalid upload data received. Please try again.')

        try:
            file_bytes = base64.b64decode(base64_data)
        except Exception:
            raise UserError('Failed to decode uploaded file. Please try again.')

        if filename.endswith('.xls'):
            raise UserError('Old .xls format is not supported. Please save your file as .xlsx and try again.')

        elif filename.endswith('.xlsx'):
            try:

                wb = openpyxl.load_workbook(BytesIO(file_bytes), read_only=True)
            except Exception as e:
                raise UserError(
                    f'Failed to open Excel file: {e}\n''Please make sure the file is a valid .xlsx file and not corrupted.')

            ws = wb.active
            headers = [
                str(cell.value).strip() if cell.value else ''
                for cell in next(ws.iter_rows(min_row=1, max_row=1))
            ]

            col_index = None
            for i, h in enumerate(headers):
                if h.lower() in ('internal reference', 'internal_reference', 'sku', 'default_code'):
                    col_index = i
                    break

            if col_index is None:
                raise UserError(
                    f'Column "Internal Reference" not found. '
                    f'Found columns: {", ".join(headers)}. '
                    f'Please use the Reference Template to create your file.'
                )

            skus = []
            for row in ws.iter_rows(min_row=2, values_only=True):
                val = row[col_index]
                if val:
                    skus.append(str(val).strip())
        else:
            raise UserError('Unsupported file format. Please upload a .xlsx or .csv file.')

        skus = [s for s in skus if s]
        if not skus:
            raise UserError('No SKUs found in the uploaded file. Please check the file content.')

        found_variants = self.env['product.product'].search([
            ('default_code', 'in', skus),
            ('active', '=', True),
            ('sale_ok', '=', True),
        ])

        found_templates = found_variants.mapped('product_tmpl_id')

        found_skus = set(found_variants.mapped('default_code'))
        not_found = [s for s in skus if s not in found_skus]

        return {
            'products': [{'id': p.id, 'name': p.name} for p in found_templates],
            'not_found': not_found,
        }

    @api.model
    def action_download_sku_template(self):
        """Generates and returns a demo SKU template Excel file."""
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('SKU Template')

        header_fmt = workbook.add_format({
            'bold': True, 'bg_color': '#4472C4',
            'font_color': '#FFFFFF', 'border': 1,
        })
        cell_fmt = workbook.add_format({'border': 1})

        sheet.write(0, 0, 'Internal Reference', header_fmt)
        sheet.set_column(0, 0, 30)

        # Add example rows
        examples = ['SKU001', 'SKU002', 'SKU003']
        for i, sku in enumerate(examples, start=1):
            sheet.write(i, 0, sku, cell_fmt)

        workbook.close()
        output.seek(0)
        file_data = base64.b64encode(output.read()).decode('utf-8')

        return {
            'filename': 'sku_template.xlsx',
            'file_data': file_data,
        }
