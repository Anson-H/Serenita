from backend.app.core.tabular_json import decode_tabular_json, encode_tabular_json


SAMPLE = {
    "corpus_version": "v1",
    "items": [
        {"item_name_zh": "丙氨酸氨基转移酶", "aliases": ["ALT"], "description": None},
        {"item_name_zh": "葡萄糖", "aliases": [], "description": None},
    ],
    "irregular": [{"a": 1}, {"b": 2}],
    "single": [{"a": 1}],
    "nested": [
        {"report": "r1", "results": [{"n": "x", "v": 1}, {"n": "y", "v": 2}]},
        {"report": "r2", "results": [{"n": "z", "v": 3}, {"n": "w", "v": 4}]},
    ],
}


def test_encode_decode_round_trip_restores_the_original_shape():
    encoded = encode_tabular_json(SAMPLE)
    assert encoded["items"]["$keys"] == ["item_name_zh", "aliases", "description"]
    assert encoded["items"]["$rows"] == [
        ["丙氨酸氨基转移酶", ["ALT"], None],
        ["葡萄糖", [], None],
    ]
    assert encoded["irregular"] == SAMPLE["irregular"]
    assert encoded["single"] == SAMPLE["single"]
    nested_rows = encoded["nested"]["$rows"]
    assert nested_rows[0][1] == {"$keys": ["n", "v"], "$rows": [["x", 1], ["y", 2]]}
    assert decode_tabular_json(encoded) == SAMPLE


def test_encode_preserves_first_logical_object_order_across_key_order_variants():
    encoded = encode_tabular_json(
        [
            {"second": 2, "first": 1},
            {"first": 3, "second": 4},
        ]
    )
    assert encoded == {
        "$keys": ["second", "first"],
        "$rows": [[2, 1], [4, 3]],
    }


def test_encode_is_idempotent_over_already_encoded_data():
    once = encode_tabular_json(SAMPLE)
    assert encode_tabular_json(once) == once


def test_decode_leaves_malformed_or_plain_shapes_untouched():
    malformed_rows = {"$keys": ["a"], "$rows": [[1], [2, 3]]}
    assert decode_tabular_json(malformed_rows) == malformed_rows
    partial = {"$keys": ["a"]}
    assert decode_tabular_json(partial) == partial
    plain = {"note": "x", "rows": [1, 2]}
    assert decode_tabular_json(plain) == plain
