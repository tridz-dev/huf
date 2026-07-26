from frappe import _

def get_data():
    return {
        'fieldname': 'tool',

        'transactions': [
            {
                'label': _('Context'),
                'items': ['Agent', 'Agent Tool Call']
            },
        ]
    }
