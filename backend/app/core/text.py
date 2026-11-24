"""Text helpers: URL slugs from Uzbek (Latin or Cyrillic) and Russian names."""

from __future__ import annotations

import re
import unicodedata

_CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ғ": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "қ": "q", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ў": "o",
    "ф": "f", "х": "x", "ҳ": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "",
    "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}  # fmt: skip
_APOSTROPHES = "ʻʼ‘’'`´"
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str, *, max_length: int = 80) -> str:
    text = value.lower()
    text = "".join(_CYRILLIC.get(ch, ch) for ch in text)
    text = "".join(ch for ch in text if ch not in _APOSTROPHES)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = _NON_ALNUM.sub("-", text).strip("-")
    return text[:max_length].rstrip("-") or "item"
