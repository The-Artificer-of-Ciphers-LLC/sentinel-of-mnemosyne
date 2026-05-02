"""Behavioral tests for sentinel_shared.embedding_codec."""
from __future__ import annotations

import numpy as np

from sentinel_shared.embedding_codec import decode_embedding, encode_embedding


def test_encode_decode_round_trip():
    vec = [0.1, -0.5, 0.0, 1.0, -1.0]
    s = encode_embedding(vec)
    assert isinstance(s, str)
    out = decode_embedding(s)
    np.testing.assert_allclose(np.array(out, dtype=np.float32), np.array(vec, dtype=np.float32))


def test_encode_accepts_list_or_ndarray_or_passthrough_str():
    vec_list = [0.5, 0.5]
    vec_arr = np.array(vec_list, dtype=np.float32)
    s_list = encode_embedding(vec_list)
    s_arr = encode_embedding(vec_arr)
    assert s_list == s_arr
    # passthrough: already-encoded string returned verbatim
    assert encode_embedding(s_list) == s_list


def test_decode_accepts_list_ndarray_or_b64_str():
    vec = [0.25, -0.25, 0.5]
    out_list = decode_embedding(vec)
    assert out_list == [0.25, -0.25, 0.5]
    assert all(isinstance(x, float) for x in out_list)

    out_arr = decode_embedding(np.array(vec, dtype=np.float32))
    assert isinstance(out_arr, list)
    np.testing.assert_allclose(out_arr, vec)

    out_b64 = decode_embedding(encode_embedding(vec))
    np.testing.assert_allclose(out_b64, vec)


def test_decode_empty_string_returns_empty_list():
    assert decode_embedding("") == []


def test_decode_invalid_b64_returns_empty_list():
    # Not valid base64 of float32 bytes — should not raise.
    out = decode_embedding("!!!not-base64!!!")
    assert out == []
