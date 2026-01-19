import json
from django import template
from django.core.serializers.json import DjangoJSONEncoder

register = template.Library()

@register.filter
def to_json(value):
    """Convert a value to JSON, handling QuerySets properly."""
    if hasattr(value, '__iter__') and not isinstance(value, (str, dict)):
        # Convert QuerySet or iterable of model instances to list of IDs
        result = []
        for item in value:
            if hasattr(item, 'id'):
                result.append(item.id)
            elif isinstance(item, dict) and 'product' in item:
                result.append(item['product'].id)
            else:
                result.append(item)
        return json.dumps(result, cls=DjangoJSONEncoder)
    return json.dumps(value, cls=DjangoJSONEncoder)

@register.filter
def extract_ids(value):
    """Extract IDs from a list of objects/dicts."""
    if hasattr(value, '__iter__') and not isinstance(value, (str, dict)):
        result = []
        for item in value:
            if hasattr(item, 'id'):
                result.append(item.id)
            elif isinstance(item, dict) and 'product' in item:
                result.append(item['product'].id)
            else:
                result.append(item)
        return result
    return value