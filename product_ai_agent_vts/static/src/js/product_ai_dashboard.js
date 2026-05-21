/** @odoo-module **/

import {registry} from "@web/core/registry";
import {Component, onMounted, onWillUnmount, useState, useRef} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

class ProductAIAgentDashboard extends Component {
    static template = "vraja_ai_dashboard_template";

    // ─────────────────────────────────────────────────────────────────────────
    // SETUP
    // ─────────────────────────────────────────────────────────────────────────

    setup() {
        this.orm = useService("orm");
        this.productSelectorRef = useRef("productSelector");

        this.state = useState({
            store: false,               // vraja_common_store value of the card
            ready: false,               // true after all data is loaded — prevents white screen on refresh
            cardId: this.props.action?.params?.card_id,

            // Form / API result state
            productData: null,          // raw data from action_get_product_ai_dashboard_data
            loading: false,             // disables buttons during async ops
            message: '',                // flash message text
            messageType: '',            // 'success' | 'danger'

            // Many2many product selector state
            selectedProducts: [],       // [{id, name}] — currently selected tag pills
            selectedProductMap: {},     // {[id]: true} — for reliable OWL checkbox reactivity
            productSearch: '',          // current text in the search input
            productDropdown: [],        // live search results shown in dropdown
            showDropdown: false,        // controls dropdown visibility
            useSalesHistory: true,
            step6Search: '',
        });

        // Close dropdown when clicking outside the product selector box
        this._outsideClickHandler = (ev) => {
            const el = this.productSelectorRef.el;
            if (el && !el.contains(ev.target)) {
                this.state.showDropdown = false;
            }
        };

        onMounted(async () => {
            document.addEventListener('mousedown', this._outsideClickHandler);

            // Fix Odoo default overflow so dashboard scrolls properly
            document.body.style.overflowY = "auto";
            const root = document.querySelector(".o_content");
            if (root) {
                root.style.overflowY = "auto";
                root.style.height = "100vh";
            }

            await this.loadCardStore();
            this.setupCollapseToggles();

            if (this.state.store === 'product_alt_acc') {
                await this.loadProductAIDashboardData();
                this.loadSelectedProducts();
                this.state.useSalesHistory = this.state.productData?.product_ai_use_sales_history ?? true;
                this._fillSelects();
            }

            // Mark as ready — template renders main content only after this
            this.state.ready = true;
        });
        onWillUnmount(() => {
            document.removeEventListener('mousedown', this._outsideClickHandler);
        });
    }

    // ─────────────────────────────────────────────────────────────────────────
    // INITIALISATION HELPERS
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Reads vraja_common_store for the current card.
     * On page refresh cardId may be missing — falls back to searching by store type.
     */
    async loadCardStore() {
        if (!this.state.cardId) {
            // Refresh case: cardId lost from URL — search for the card directly
            const cards = await this.orm.searchRead(
                'vraja.ai.card',
                [['vraja_common_store', '=', 'product_alt_acc']],
                ['id', 'vraja_common_store'],
                {limit: 1}
            );
            if (cards.length) {
                this.state.cardId = cards[0].id;
                this.state.store = cards[0].vraja_common_store;
            }
            return;
        }

        const [card] = await this.orm.read(
            "vraja.ai.card",
            [this.state.cardId],
            ["vraja_common_store"]
        );
        this.state.store = card?.vraja_common_store || false;
    }

    /**
     * Wires up Bootstrap collapse chevron icons after DOM is ready.
     */
    setupCollapseToggles() {
        document.querySelectorAll(".dashboard-toggle").forEach((toggle) => {
            const target = document.querySelector(toggle.getAttribute("data-bs-target"));
            const icon = toggle.querySelector(".toggle-icon");
            if (!target || !icon) return;
            target.addEventListener("show.bs.collapse", () => {
                icon.classList.replace("fa-chevron-up", "fa-chevron-down");
            });
            target.addEventListener("hide.bs.collapse", () => {
                icon.classList.replace("fa-chevron-down", "fa-chevron-up");
            });
        });
    }

    // ─────────────────────────────────────────────────────────────────────────
    // DATA LOADING
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Loads all saved card settings and AI results from Python.
     */
    async loadProductAIDashboardData() {
        if (!this.state.cardId) return;
        try {
            this.state.productData = await this.orm.call(
                'vraja.ai.card',
                'action_get_product_ai_dashboard_data',
                [this.state.cardId]
            );
        } catch (e) {
            console.error('Failed to load product AI data:', e);
        }
    }

    /**
     * Restores selected product tag pills from productData.
     * No extra RPC needed — action_get_product_ai_dashboard_data already returns selected_products.
     */
    loadSelectedProducts() {
        const products = this.state.productData?.selected_products || [];
        this.state.selectedProducts = products.map(p => ({id: p.id, name: p.name}));
        const map = {};
        products.forEach(p => {
            map[p.id] = true;
        });
        this.state.selectedProductMap = map;
    }

    _fillSelects() {
        if (!this.state.productData) return;
        const d = this.state.productData;
        const setSelect = (id, val) => {
            const el = document.getElementById(id);
            if (el && val) el.value = val;
        };
        setSelect('product_ai_suggestion_type', d.product_ai_suggestion_type);
        setSelect('product_ai_min_confidence', d.product_ai_min_confidence);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // MANY2MANY PRODUCT SELECTOR
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Fires on every keystroke — live ilike search, excludes already selected products.
     */
    async onProductSearchInput(ev) {
        const query = ev.target.value;
        this.state.productSearch = query;

        if (!query.trim()) {
            this.state.productDropdown = [];
            this.state.showDropdown = false;  // hide when input is cleared
            return;
        }

        const excludeIds = this.state.selectedProducts.map(p => p.id);
        this.state.productDropdown = await this.orm.searchRead(
            'product.template',
            [
                ['active', '=', true],
                ['sale_ok', '=', true],
                ['name', 'ilike', query],
                ['id', 'not in', excludeIds],
            ],
            ['id', 'name'],
            {limit: 0}  // 0 = no limit, return all matches
        );
        this.state.showDropdown = this.state.productDropdown.length > 0;
    }

    /**
     * Opens dropdown on focus — loads all products if no search is active.
     */
    async onProductSearchFocus() {
        if (this.state.productDropdown.length) {
            this.state.showDropdown = true;
            return;
        }
        const excludeIds = this.state.selectedProducts.map(p => p.id);
        this.state.productDropdown = await this.orm.searchRead(
            'product.template',
            [['active', '=', true], ['sale_ok', '=', true], ['id', 'not in', excludeIds]],
            ['id', 'name'],
            {limit: 0}
        );
        this.state.showDropdown = this.state.productDropdown.length > 0;
    }

    /**
     * Toggles product checkbox — adds or removes from selected tags.
     * Does NOT re-fetch dropdown so OWL checkbox reactivity is preserved.
     */
    onToggleProductCheckbox(product) {
        const map = {...this.state.selectedProductMap};
        if (map[product.id]) {
            delete map[product.id];
            this.state.selectedProducts = this.state.selectedProducts.filter(p => p.id !== product.id);
        } else {
            map[product.id] = true;
            this.state.selectedProducts = [...this.state.selectedProducts, product];
        }
        this.state.selectedProductMap = {...map};
        this.state.showDropdown = true;
    }

    /**
     * Removes a tag pill via the ✕ button.
     */
    onRemoveProduct(productId) {
        const map = {...this.state.selectedProductMap};
        delete map[productId];
        this.state.selectedProductMap = map;
        this.state.selectedProducts = this.state.selectedProducts.filter(p => p.id !== productId);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // FLASH MESSAGE
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Shows a temporary bootstrap alert. Auto-clears after 4 seconds.
     */
    _showMessage(msg, type = 'success') {
        this.state.message = msg;
        this.state.messageType = type;
        setTimeout(() => {
            this.state.message = '';
            this.state.messageType = '';
        }, 4000);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // AI RESULT HELPERS
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Parses product_ai_result_json into a flat array for the Step 6 results table.
     * Returns: [{product_id, alternatives: [], accessories: []}, ...]
     */
    getAIResults() {
        if (!this.state.productData?.product_ai_result_json) return [];
        try {
            return Object.entries(
                JSON.parse(this.state.productData.product_ai_result_json)
            ).map(([pid, data]) => ({
                product_id: pid,
                product_name: data.product_name || pid,
                alternatives: data.alternatives || [],
                accessories: data.accessories || [],
            }));
        } catch {
            return [];
        }
    }

// ── Step 6 search and filter ──────────────────────────────────────────────

    onStep6Search(ev) {
        this.state.step6Search = ev.target.value.toLowerCase();
    }

    getFilteredAIResults() {
        const q = this.state.step6Search;
        const results = this.getAIResults();
        if (!q) return results;
        return results.filter(r =>
            (r.product_name || '').toLowerCase().includes(q) ||
            String(r.product_id).includes(q)
        );
    }


    // ─────────────────────────────────────────────────────────────────────────
    // ACTIONS
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Saves all form values to the card and regenerates the Excel preview file.
     */
    async onProductAISave() {
        const getEl = (id) => document.getElementById(id);
        const getVal = (id, fb) => getEl(id)?.value || fb;
        const getChk = (id) => getEl(id)?.checked || false;

        const values = {
            product_ai_business_info: getVal('product_ai_business_info', ''),
            product_ai_suggestion_type: getVal('product_ai_suggestion_type', 'both'),
            product_ai_price_tolerance: parseFloat(getVal('product_ai_price_tolerance', 15)),
            product_ai_max_suggestions: parseInt(getVal('product_ai_max_suggestions', 5)),
            product_ai_min_confidence: getVal('product_ai_min_confidence', 'all'),
            product_ai_sales_history_days: parseInt(getVal('product_ai_sales_history_days', 30)),

            product_ai_use_category: getChk('product_ai_use_category'),
            product_ai_use_tags: getChk('product_ai_use_tags'),
            product_ai_use_price: getChk('product_ai_use_price'),
            product_ai_use_attributes: getChk('product_ai_use_attributes'),
            product_ai_use_sales_history: getChk('product_ai_use_sales_history'),

            // Send raw IDs — Python wraps into [(6, 0, ids)]
            product_ai_selected_product_ids: this.state.selectedProducts.map(p => p.id),
        };

        try {
            this.state.loading = true;
            await this.orm.call(
                'vraja.ai.card',
                'action_save_product_ai_dashboard_data',
                [this.state.cardId, values]
            );
            await this.loadProductAIDashboardData();
            this._showMessage('Settings saved successfully.', 'success');
        } catch (e) {
            this._showMessage('Failed to save: ' + (e.message || String(e)), 'danger');
        } finally {
            this.state.loading = false;
        }
    }

    /**
     * Sends selected products to OpenAI for analysis.
     */
    async onProductAIRun() {
        try {
            this.state.loading = true;
            await this.orm.call('vraja.ai.card', 'action_run_product_ai', [this.state.cardId]);
            await this.loadProductAIDashboardData();
            this._showMessage('AI analysis completed successfully.', 'success');
        } catch (e) {
            // Extract exact error message from Odoo RPC error
            const msg = e?.data?.message || e?.message || String(e);
            this._showMessage(msg, 'danger');
            await this.loadProductAIDashboardData();
        } finally {
            this.state.loading = false;
        }
    }

    /**
     * Applies AI suggestions (alternatives/accessories) to Odoo products.
     */
    async onProductAIApply() {
        if (!confirm('This will overwrite existing alternative and accessory products. Continue?')) return;
        try {
            this.state.loading = true;
            const result = await this.orm.call(
                'vraja.ai.card',
                'action_apply_product_ai_suggestions',
                [this.state.cardId]
            );
            await this.loadProductAIDashboardData();
            this._showMessage(`Successfully applied to ${result.applied} product(s).`, 'success');
        } catch (e) {
            this._showMessage('Apply Error: ' + (e.message || String(e)), 'danger');
        } finally {
            this.state.loading = false;
        }
    }
}

// Force-replace the base dashboard action with this extended component
registry.category("actions").add("vraja_ai_dashboard_template", ProductAIAgentDashboard, {force: true});