from frappe import _

def get_data():
    return {
        'fieldname': 'agent_run',

        'transactions': [
           {
                'label': _('Context'),
                'items': ['Agent Tool Call', 'Agent Message']
            },
        ]
    }
