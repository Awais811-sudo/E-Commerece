# your_app/templatetags/math_filters.py
# from django import template

# register = template.Library()

# @register.filter(name='subtract')
# def subtract(value, arg):
#     """Subtracts arg from value."""
#     return value - arg

# print("Custom filter 'subtract' registered successfully!")  # Debug statement


from django import template

register = template.Library()

@register.filter
def subtract(value, arg):
    """Subtract the arg from the value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        try:
            return value - arg
        except Exception:
            return '' # Return the original value if conversion fails
    

@register.filter(name='float')
def float_filter(value):
    """
    Converts the given value to a float.
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return value

@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except:
        return value