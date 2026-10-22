import unicodedata


def safe_csv_cell(value):
    """Neutralize spreadsheet formulas after leading whitespace/control chars."""
    value = "" if value is None else str(value)
    probe = value
    while probe and (probe[0].isspace() or unicodedata.category(probe[0]) in {"Cc", "Cf"}):
        probe = probe[1:]
    if probe.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
