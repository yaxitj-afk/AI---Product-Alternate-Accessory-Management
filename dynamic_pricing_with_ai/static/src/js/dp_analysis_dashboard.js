/** @odoo-module **/

import {Component, onMounted, onWillUnmount, useState} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

export class DynamicPricingAnalysisDashboard extends Component {
    setup() {
        this.orm = useService("orm");

        this.state = useState({
            cardId: this.props.action?.params?.card_id,
            loading: true,
            error: "",
            period: "last_7_days",
            limit: 5,
            dateFrom: "",
            dateTo: "",
            data: {},
        });

        this.requestSeq = 0;
        this.moneyFormatter = null;
        this.numberFormatter = new Intl.NumberFormat(undefined, {maximumFractionDigits: 2});

        onMounted(async () => {
            this.enableDashboardScroll();
            await this.loadDashboard();
        });

        onWillUnmount(() => {
            this.restoreDashboardScroll();
        });
    }

    enableDashboardScroll() {
        // Target every ancestor that could clip height
        const selectors = [
            ".o_content",
            ".o_action_manager",
            ".o_view_controller",
            ".o_action",
        ];
        this._scrollTargets = [];
        selectors.forEach(sel => {
            const el = document.querySelector(sel);
            if (el) {
                this._scrollTargets.push({
                    el,
                    prevOverflow: el.style.overflowY,
                    prevHeight: el.style.height,
                    prevMinHeight: el.style.minHeight,
                });
                el.style.overflowY = "visible";
                el.style.height = "auto";
                el.style.minHeight = "unset";
            }
        });

        // Let the outermost app container scroll
        const appRoot = document.querySelector(".o_web_client") || document.body;
        this._appRoot = appRoot;
        this._prevAppOverflow = appRoot.style.overflowY;
        appRoot.style.overflowY = "auto";

        this._prevBodyOverflow = document.body.style.overflowY;
        document.body.style.overflowY = "auto";
    }

    restoreDashboardScroll() {
        (this._scrollTargets || []).forEach(({el, prevOverflow, prevHeight, prevMinHeight}) => {
            el.style.overflowY = prevOverflow || "";
            el.style.height = prevHeight || "";
            el.style.minHeight = prevMinHeight || "";
        });
        if (this._appRoot) {
            this._appRoot.style.overflowY = this._prevAppOverflow || "";
        }
        document.body.style.overflowY = this._prevBodyOverflow || "";
    }

    async loadDashboard() {
        const requestId = ++this.requestSeq;
        if (!this.state.cardId) {
            await this.ensureCardId();
            if (!this.state.cardId) {
                this.state.error = "Dynamic pricing card was not found.";
                this.state.loading = false;
                return;
            }
        }
        this.state.loading = true;
        this.state.error = "";
        try {
            const data = await this.orm.call(
                "vraja.ai.card",
                "action_get_dp_analysis_dashboard_data",
                [this.state.cardId, this.getFilters()]
            );
            if (requestId === this.requestSeq) {
                this.state.data = data;
                this.moneyFormatter = null;
            }
        } catch (error) {
            if (requestId === this.requestSeq) {
                this.state.error = error?.data?.message || error?.message || String(error);
            }
        } finally {
            if (requestId === this.requestSeq) {
                this.state.loading = false;
            }
        }
    }

    async ensureCardId() {
        try {
            const cardId = await this.orm.call("vraja.ai.card", "action_dp_get_default_card_id", []);
            if (cardId) this.state.cardId = cardId;
        } catch (error) {
            this.state.error = error?.data?.message || error?.message || String(error);
        }
    }

    getFilters() {
        return {
            period: this.state.period,
            limit: Number(this.state.limit),
            date_from: this.state.dateFrom,
            date_to: this.state.dateTo,
        };
    }

    async setPeriod(period) {
        if (this.state.period === period || this.state.loading) return;
        this.state.period = period;
        if (period !== "custom") await this.loadDashboard();
    }

    async setLimit(limit) {
        if (Number(this.state.limit) === Number(limit) || this.state.loading) return;
        this.state.limit = Number(limit);
        await this.loadDashboard();
    }

    async onCustomDateChange(field, ev) {
        this.state[field] = ev.target.value;
        if (this.state.period === "custom" && this.state.dateFrom && this.state.dateTo) {
            await this.loadDashboard();
        }
    }

    periodButtonClass(period) {
        return `dpad-pill-btn ${this.state.period === period ? "active" : ""}`;
    }

    limitButtonClass(limit) {
        return `dpad-pill-btn ${Number(this.state.limit) === Number(limit) ? "active" : ""}`;
    }

    // ── Data getters ──────────────────────────────────────────────────────────

    get card() {
        return this.state.data.card || {};
    }

    get filters() {
        return this.state.data.filters || {};
    }

    get summary() {
        return this.state.data.summary || {};
    }

    get topProducts() {
        return this.state.data.top_products || [];
    }

    get decisionMix() {
        return this.state.data.decision_mix || [];
    }

    get segmentData() {
        return this.state.data.segment_data || [];
    }

    get atRisk() {
        return this.state.data.at_risk || [];
    }

    get topImprovers() {
        return this.state.data.top_improvers || [];
    }

    get heroProduct() {
        return this.topProducts[0] || null;
    }

    get hasProducts() {
        return this.topProducts.length > 0;
    }

    get hasSegments() {
        return this.segmentData.length > 0;
    }

    get maxRevenue() {
        return Math.max(...this.topProducts.map(r => r.revenue || 0), 1);
    }

    // ── Formatters ────────────────────────────────────────────────────────────

    formatMoney(value) {
        if (!this.moneyFormatter) {
            this.moneyFormatter = new Intl.NumberFormat(undefined, {
                style: "currency",
                currency: this.state.data.currency || "USD",
                maximumFractionDigits: 2,
            });
        }
        return this.moneyFormatter.format(value || 0);
    }

    formatNumber(value) {
        return this.numberFormatter.format(value || 0);
    }

    formatPct(value) {
        const v = value || 0;
        return (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
    }

    // ── Decision helpers ──────────────────────────────────────────────────────

    decisionLabel(decision) {
        return {
            increase: "Increase",
            decrease: "Decrease",
            hold: "Hold",
            skip: "Skip",
            not_analyzed: "Not Analysed"
        }[decision] || decision;
    }

    decisionClass(decision) {
        return `dpad-badge dpad-badge--${decision || "not_analyzed"}`;
    }

    decisionIcon(decision) {
        return {
            increase: "fa-arrow-up",
            decrease: "fa-arrow-down",
            hold: "fa-minus",
            skip: "fa-ban",
            not_analyzed: "fa-question"
        }[decision] || "fa-question";
    }

    marginDeltaClass(before, after) {
        if (after > before) return "dpad-positive";
        if (after < before) return "dpad-negative";
        return "dpad-neutral";
    }

    barWidth(value, max) {
        return `${Math.max(4, (value / (max || 1)) * 100)}%`;
    }

    marginBarWidth(margin) {
        return `${Math.min(100, Math.max(0, margin))}%`;
    }
}

DynamicPricingAnalysisDashboard.template = "dynamic_pricing_analysis_dashboard_template";
registry.category("actions").add("dynamic_pricing_analysis_dashboard", DynamicPricingAnalysisDashboard);