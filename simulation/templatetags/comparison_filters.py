# templatetags/comparison_filters.py

from django import template
from decimal import Decimal

register = template.Library()

@register.filter(name='get')
def get_dict_value(dictionary, key):
    """Get value from dictionary by key"""
    try:
        # Convert key to string if it's a number
        key = str(key) if isinstance(key, (int, float)) else key
        return dictionary.get(key)
    except (TypeError, AttributeError):
        return None

@register.filter(name='to_int')
def to_int(value):
    """Convert a value to integer"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

@register.filter
def filter_by_year(queryset, year):
    """Get simulation data for a specific year"""
    return queryset.filter(annee=year).first()

@register.filter
def subtract(value, arg):
    """Subtract two decimal values"""
    try:
        return Decimal(str(value)) - Decimal(str(arg))
    except:
        return 0