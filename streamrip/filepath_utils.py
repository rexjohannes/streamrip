from string import printable

from pathvalidate import sanitize_filename, sanitize_filepath  # type: ignore

ALLOWED_CHARS = set(printable)


# TODO: remove this when new pathvalidate release arrives with https://github.com/thombashi/pathvalidate/pull/48
def truncate_str(text: str) -> str:
    str_bytes = text.encode()
    str_bytes = str_bytes[:255]
    return str_bytes.decode(errors="ignore")


def replace_umlauts(s):
    return s.replace("Ä", "Ae").replace("ä", "ae").replace("Ö", "Oe").replace("ö", "oe").replace("Ü", "Ue").replace("ü", "ue").replace("ß", "ss")


def clean_filename(fn: str, restrict: bool = False) -> str:
    path = truncate_str(str(sanitize_filename(fn)))
    path = replace_umlauts(path)
    if restrict:
        path = "".join(c for c in path if c in ALLOWED_CHARS)

    return path


def clean_filepath(fn: str, restrict: bool = False) -> str:
    path = str(sanitize_filepath(fn))
    path = replace_umlauts(path)
    if restrict:
        path = "".join(c for c in path if c in ALLOWED_CHARS)

    return path
