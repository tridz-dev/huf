from frappe import _

def get_data():
    return {
        'fieldname': 'conversation',

        'transactions': [
            {
                'label': _('Execution'),
                'items': ['Agent Run']
            },
            {
                'label': _('Context'),
                'items': ['Agent Tool Call', 'Agent Message']
            },
        ]
    }
