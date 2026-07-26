from frappe import _

def get_data():
    return {
        'fieldname': 'model',

        'transactions': [
            {
                'label': _('Context'),
                'items': ['Agent', 'Agent Message']
            },
        ]
    }
