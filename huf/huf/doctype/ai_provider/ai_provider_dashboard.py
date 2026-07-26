from frappe import _

def get_data():
    return {
        'fieldname': 'provider',

        'transactions': [
            {
                'label': _('Context'),
                'items': ['AI Model','Agent', 'Agent Message']
            },
        ]
    }
