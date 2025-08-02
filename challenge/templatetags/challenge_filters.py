from django import template
from typing import Optional, Dict, Any, List
from challenge.models import Challenge

register = template.Library()


@register.filter
def get_item(dictionary: Optional[Dict[str, Any]], key: str) -> Optional[Any]:
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def sort_challenges(challenges: List[Challenge]) -> List[Challenge]:
    return sorted(challenges, key=lambda x: (x.points, x.name))
