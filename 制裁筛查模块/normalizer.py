import re
import unicodedata


CORPORATE_SUFFIXES = {
    "CO",
    "CORP",
    "INC",
    "LIMITED",
    "LLC",
    "LTD",
}


def normalize_name(name):
    if name is None:
        return ""

    name = unicodedata.normalize(
        "NFKC",
        str(name)
    ).casefold()

    name = re.sub(
        r"[-.,'\"/()]+",
        " ",
        name
    )

    tokens = [
        token
        for token in name.split()
        if token.upper() not in CORPORATE_SUFFIXES
    ]

    return " ".join(tokens).upper()
