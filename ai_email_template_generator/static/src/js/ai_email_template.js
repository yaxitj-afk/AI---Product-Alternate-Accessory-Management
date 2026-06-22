/** @odoo-module **/

import {Component, useState, onWillStart, onWillUnmount} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {standardFieldProps} from "@web/views/fields/standard_field_props";
import {useService} from "@web/core/utils/hooks";
//
// const STAGES = [
//     { key: "gathering_data", label: "Gathering data" },
//     { key: "calling_api", label: "Calling AI provider" },
//     { key: "parsing_response", label: "Parsing response" },
//     { key: "generating_template", label: "Generating template" },
//     { key: "done", label: "Generated successfully" },
// ];
//
// class AiProgressWidget extends Component {
//     setup() {
//         this.orm = useService("orm");
//         this.state = useState({ current: this.props.record.data.state });
//         this.pollInterval = null;
//
//         onWillStart(() => {
//             this.startPolling();
//         });
//         onWillUnmount(() => {
//             if (this.pollInterval) {
//                 clearInterval(this.pollInterval);
//             }
//         });
//     }
//
//     startPolling() {
//         // ADDED: polls the record's own state every 800ms, independent
//         // of the main button-click request still in flight - this is
//         // what makes the progress visually "live"
//         this.pollInterval = setInterval(async () => {
//             const result = await this.orm.read(
//                 this.props.record.resModel,
//                 [this.props.record.resId],
//                 ["state"]
//             );
//             if (result && result[0]) {
//                 this.state.current = result[0].state;
//                 if (this.state.current === "done" || this.state.current === "failed") {
//                     clearInterval(this.pollInterval);
//                 }
//             }
//         }, 800);
//     }
//
//     isDoneStage(stageKey) {
//         const order = STAGES.map((s) => s.key);
//         return order.indexOf(stageKey) < order.indexOf(this.state.current) || this.state.current === "done";
//     }
//
//     isCurrentStage(stageKey) {
//         return stageKey === this.state.current;
//     }
// }
//
// AiProgressWidget.template = "ai_email_template_generator.AiProgressWidget";
// AiProgressWidget.props = ["*"];
//
// registry.category("fields").add("ai_progress_tracker", AiProgressWidget);
class AiCardSelector extends Component {
    setup() {
        this.state = useState({
            selected: this.props.record.data[this.props.name]
        });
    }

    selectCard(value) {
        this.props.record.update({[this.props.name]: value});
        this.state.selected = value;
    }

     isSelected(value) {
        return this.props.record.data[this.props.name] === value;
    }
}

AiCardSelector.template = "ai_email_template_generator.AiCardSelector";
AiCardSelector.props = {
    ...standardFieldProps,
};


registry.category("fields").add("ai_card_selector", {
    component: AiCardSelector,
});