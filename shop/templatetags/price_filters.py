from django import template

register = template.Library()

@register.filter
def sub(value, arg):
    """Subtract the arg from the value"""
    return value - arg

@register.filter
def multiply(value, arg):
    """Multiply value by arg"""
    return value * arg