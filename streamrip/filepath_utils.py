from string import printable
import re
from pathvalidate import sanitize_filename, sanitize_filepath

ALLOWED_CHARS = set(printable)

def replace_german_chars(s: str) -> str:
    replacements = {
        'Ä': 'Ae',
        'ä': 'ae',
        'Ö': 'Oe',
        'ö': 'oe',
        'Ü': 'Ue',
        'ü': 'ue',
        'ß': 'ss'
    }
    pattern = re.compile('|'.join(re.escape(key) for key in replacements.keys()))
    return pattern.sub(lambda x: replacements[x.group()], s)

def clean_filename(fn: str, restrict: bool = False) -> str:
    path = str(sanitize_filename(fn))
    if restrict:
        path = "".join(c for c in path if c in ALLOWED_CHARS)
    truncate_to = 60
    if truncate_to > 0 and len(path) > truncate_to:
            path = path[: truncate_to]

    return path


def clean_filepath(fn: str, restrict: bool = False) -> str:
    path = str(sanitize_filepath(fn))
    if restrict:
        path = "".join(c for c in path if c in ALLOWED_CHARS)

    return path
