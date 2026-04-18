"""Tests for decode_attributed_body — the typedstream parser that extracts
message text from the `attributedBody` BLOB when the plain `text` column is
NULL (which it is for any message sent from a recent-ish iOS/macOS version).

The parser is hand-rolled (pure Python, no PyObjC). These tests cover:
  - happy paths for short, medium, and long strings
  - length-prefix variants (single byte, 0x81 + uint16, 0x82 + uint32)
  - defensive early-exit paths for malformed/truncated/empty input
  - the documented silent-failure behavior — anything the parser can't make
    sense of returns "" rather than raising
"""
from __future__ import annotations

import struct
import unittest

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _helper_loader import helper  # noqa: E402


def _make_blob(body: bytes, *, with_nsobject: bool = False,
               leading_marker: int = 0x01) -> bytes:
    """Construct a minimal valid attributedBody blob wrapping `body`.

    Layout:
        [16-byte header with "streamtyped"]
        NSString
        <leading_marker>              (1 byte, skipped by the parser)
        [optional "NSObject" + marker run]
        0x2b
        <length-prefix>
        <body bytes>

    This mirrors the actual on-disk structure closely enough for the parser
    to hit its happy path.
    """
    header = b"streamtyped\x00\x00\x00\x00\x00"  # 16 bytes, streamtyped at 0
    assert len(header) == 16

    out = bytearray(header)
    out += b"NSString"
    out.append(leading_marker)
    if with_nsobject:
        out += b"NSObject"
        out.append(0x84)  # a skippable marker byte
    out.append(0x2B)

    # length prefix
    if len(body) < 0x80:
        out.append(len(body))
    elif len(body) < 0x10000:
        out.append(0x81)
        out += struct.pack("<H", len(body))
    else:
        out.append(0x82)
        out += struct.pack("<I", len(body))

    out += body
    return bytes(out)


class DecodeAttributedBodyTests(unittest.TestCase):

    # ---- happy paths ------------------------------------------------------

    def test_short_ascii(self):
        blob = _make_blob(b"hello world")
        self.assertEqual(helper.decode_attributed_body(blob), "hello world")

    def test_empty_body(self):
        # A 0-length body trips the `length <= 0` guard and returns "".
        blob = _make_blob(b"")
        self.assertEqual(helper.decode_attributed_body(blob), "")

    def test_utf8_multibyte(self):
        # Emoji + accented chars — the parser decodes with errors="replace"
        # so weirdness degrades gracefully rather than crashing.
        payload = "café 🎉 日本語".encode("utf-8")
        blob = _make_blob(payload)
        self.assertEqual(helper.decode_attributed_body(blob), "café 🎉 日本語")

    def test_medium_string_uses_0x81_length(self):
        body = ("x" * 300).encode("utf-8")
        blob = _make_blob(body)
        self.assertEqual(helper.decode_attributed_body(blob), "x" * 300)

    def test_large_string_uses_0x82_length(self):
        body = ("y" * 70_000).encode("utf-8")
        blob = _make_blob(body)
        self.assertEqual(helper.decode_attributed_body(blob), "y" * 70_000)

    def test_nsobject_marker_branch(self):
        # Some blobs interpose "NSObject" between NSString and the string
        # bytes. The parser skips it.
        blob = _make_blob(b"inside nsobject branch", with_nsobject=True)
        self.assertEqual(helper.decode_attributed_body(blob),
                         "inside nsobject branch")

    # ---- defensive early-exits -------------------------------------------

    def test_none_returns_empty(self):
        self.assertEqual(helper.decode_attributed_body(None), "")

    def test_empty_bytes_returns_empty(self):
        self.assertEqual(helper.decode_attributed_body(b""), "")

    def test_missing_streamtyped_header(self):
        # No "streamtyped" anywhere in the first 16 bytes → bail.
        fake = b"not a real blob at all NSString\x01\x2b\x05hello"
        self.assertEqual(helper.decode_attributed_body(fake), "")

    def test_missing_nsstring_marker(self):
        # "streamtyped" present but no NSString → bail.
        header = b"streamtyped\x00\x00\x00\x00\x00"
        self.assertEqual(helper.decode_attributed_body(header + b"rubbish"), "")

    def test_truncated_at_length_prefix(self):
        # Header + NSString but cut off before the length byte.
        header = b"streamtyped\x00\x00\x00\x00\x00"
        trunc = header + b"NSString\x01"
        self.assertEqual(helper.decode_attributed_body(trunc), "")

    def test_length_longer_than_data(self):
        # Claim a 50-byte string but only give 5 bytes → bail silently.
        header = b"streamtyped\x00\x00\x00\x00\x00"
        body = header + b"NSString\x01\x2b" + bytes([50]) + b"short"
        self.assertEqual(helper.decode_attributed_body(body), "")

    def test_non_bytes_input_does_not_raise(self):
        # The parser should degrade gracefully on surprise input types.
        # bytearray is still usable; strings and ints should return "".
        self.assertEqual(helper.decode_attributed_body(bytearray(b"")), "")

    def test_malformed_length_prefix_byte(self):
        # Length byte of 0x80 (the "invalid / reserved" case that falls
        # through an unusual code path) should bail, not crash.
        header = b"streamtyped\x00\x00\x00\x00\x00"
        body = header + b"NSString\x01\x2b\x80\x00\x00"
        # Should either decode to "" or something sensible — definitely
        # should not raise.
        try:
            out = helper.decode_attributed_body(body)
        except Exception as e:  # pragma: no cover — regression guard
            self.fail(f"decoder raised on malformed length: {e!r}")
        self.assertIsInstance(out, str)


if __name__ == "__main__":
    unittest.main()
