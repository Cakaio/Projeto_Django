# ronda/templatetags/ronda_extras.py
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key, {})
    return {}
