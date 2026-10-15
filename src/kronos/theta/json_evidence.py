"""Bounded pure JSON representation contract for later TE-04B retention.

Offsets are UTF-8 byte offsets, end-exclusive. A child is the exact JSON VALUE
at answers.<subject>, excluding the member name/colon/surrounding whitespace.
No file reading, intake, acceptance or persistence happens here.
"""
from dataclasses import dataclass
import json
import math

from kronos.theta.contracts import digest, encode
from kronos.theta.schema_v3 import MAX_DEPTH, MAX_NODES, V3Error, check


@dataclass(frozen=True, slots=True)
class JsonRepresentation:
    start: int
    end: int
    raw_bytes: bytes
    raw_sha256: str
    canonical_sha256: str


def parse_representations(payload: bytes, *, maximum: int):
    check(type(payload) is bytes and 0 < len(payload) <= maximum, "SIZE")
    try:
        text = payload.decode("utf-8")
    except UnicodeError:
        raise V3Error("THETA_V3_JSON") from None
    spans = {}
    nodes = 0
    decoder = json.JSONDecoder()

    def whitespace(i):
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        return i

    def scan(i, path, depth):
        nonlocal nodes
        nodes += 1
        check(depth <= MAX_DEPTH and nodes <= MAX_NODES, "SIZE")
        i = whitespace(i)
        check(i < len(text), "JSON")
        if text[i] == "{":
            i = whitespace(i + 1)
            seen = set()
            if i < len(text) and text[i] == "}":
                return i + 1
            while True:
                key, end = decoder.raw_decode(text, i)
                check(type(key) is str, "JSON")
                check(key not in seen, "DUPLICATE_KEY")
                seen.add(key)
                i = whitespace(end)
                check(i < len(text) and text[i] == ":", "JSON")
                i = whitespace(i + 1)
                value_start = i
                i = scan(i, (*path, key), depth + 1)
                if len(path) == 1 and path[0] == "answers":
                    spans[key] = (value_start, i)
                i = whitespace(i)
                check(i < len(text), "JSON")
                if text[i] == "}":
                    return i + 1
                check(text[i] == ",", "JSON")
                i = whitespace(i + 1)
        elif text[i] == "[":
            i = whitespace(i + 1)
            if i < len(text) and text[i] == "]":
                return i + 1
            index = 0
            while True:
                i = whitespace(scan(i, (*path, index), depth + 1))
                index += 1
                check(i < len(text), "JSON")
                if text[i] == "]":
                    return i + 1
                check(text[i] == ",", "JSON")
                i = whitespace(i + 1)
        else:
            value, end = decoder.raw_decode(text, i)
            check(not isinstance(value, float) or math.isfinite(value), "NONFINITE")
            check(not isinstance(value, str) or _utf8(value), "JSON")
            return end

    def pairs(items):
        result = {}
        for key, value in items:
            check(key not in result, "DUPLICATE_KEY")
            result[key] = value
        return result

    def nonfinite(_):
        raise V3Error("THETA_V3_NONFINITE")

    try:
        end = whitespace(scan(0, (), 0))
        check(end == len(text), "JSON")
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)
        check(type(value) is dict, "JSON")
        representations = {}
        for subject, (start, end) in spans.items():
            raw = text[start:end].encode("utf-8")
            representations[subject] = JsonRepresentation(
                len(text[:start].encode("utf-8")), len(text[:end].encode("utf-8")),
                raw, digest(raw), digest(encode(value["answers"][subject])))
        return value, representations
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError):
        raise V3Error("THETA_V3_JSON") from None


def _utf8(value):
    try:
        value.encode("utf-8")
        return True
    except UnicodeError:
        return False
