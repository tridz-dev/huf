from frappe import _

def get_data():
    return {
        'fieldname': 'agent',

        'transactions': [
            {
                'label': _('Execution'),
                'items': ['Agent Run','Agent Trigger']
            },
            {
                'label': _('Context'),
                'items': ['Agent Conversation', 'Agent Message']
            },
        ]
    }
