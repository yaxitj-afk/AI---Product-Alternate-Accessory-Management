from . import models


def _post_init_generate_product_report(env):

    card_obj = env['vraja.ai.card'].sudo()
    existing_card = card_obj.search([('vraja_common_card_name', '=', 'Product Alternate & Accessory')], limit=1)

    if not existing_card:
        card_obj.create({
            'vraja_common_card_name': 'Product Alternate & Accessory',
            'vraja_common_card_description': 'Add product alternate and accessories based on criteria selected.',
            'vraja_common_card_active': True,
            'vraja_common_store': 'product_alt_acc',
        })

def _uninstall_product_alt_acc_ai(env):
    card_obj = env['vraja.ai.card'].sudo()

    cards = card_obj.search([('vraja_common_card_name', '=', 'Product Alternate & Accessory')], limit=1)

    if cards:
        cards.unlink()
