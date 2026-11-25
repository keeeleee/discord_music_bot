import math
import re

from flask import request

from config import MAX_GROUP_LENGTH

COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def is_valid_snowflake(value):
    return isinstance(value, str) and value.isdigit() and len(value) <= 20


def is_valid_colour(value):
    """A #rrggbb colour (None is not a colour; callers decide what None means)."""
    return isinstance(value, str) and bool(COLOR_RE.match(value))


def is_finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalise_group(value):
    """Returns the group name (stripped, '' for none), or None if the value is not usable."""
    if value is None:
        return ""
    if not isinstance(value, str) or len(value.strip()) > MAX_GROUP_LENGTH:
        return None
    return value.strip()
