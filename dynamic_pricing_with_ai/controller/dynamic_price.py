# -*- coding: utf-8 -*-
"""
Dynamic Pricing AI — HTTP Controller
Registers the /dynamic-pricing/dashboard route that serves the XML template.
All data is loaded client-side via Odoo JSON-RPC (call_kw) from the JS layer.
"""

from odoo import http
from odoo.http import request


class DynamicPricingController(http.Controller):

    @http.route(
        '/dynamic-pricing/dashboard',
        type='http',
        auth='user',
        website=False,
    )
    def dashboard(self, **kwargs):
        """
        Render the Dynamic Pricing AI dashboard page.
        The HTML template loads CSS + JS as Odoo static assets.
        Product data is fetched dynamically by JS via JSON-RPC.
        """
        return request.render(
            'dynamic_pricing_with_ai.dynamic_pricing_dashboard',
            {}
        )