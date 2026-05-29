{
    "name": "Account Payment Sequence",
    "version": "18.0.1.0.1",
    "license": "LGPL-3",
    "category": "Accounting",
    "summary": "Custom sequence for payments",
    "depends": ["account"],
    "data": [
        "data/ir_sequence_data.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
