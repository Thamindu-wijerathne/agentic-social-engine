import json
from typing import Any


def extract_json_payload(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for start_char in ("[", "{"):
        start = text.find(start_char)
        while start != -1:
            try:
                obj, _ = decoder.raw_decode(text[start:])
                return obj
            except json.JSONDecodeError:
                start = text.find(start_char, start + 1)
    return None
