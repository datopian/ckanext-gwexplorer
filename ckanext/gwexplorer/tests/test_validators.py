"""Unit tests for the gw_spec validator. No database or running app required."""
import pytest

import ckan.plugins.toolkit as tk

import ckanext.gwexplorer.validators as validators


def test_empty_string_passes_through():
    assert validators.gwexplorer_valid_spec("") == ""


def test_none_passes_through():
    assert validators.gwexplorer_valid_spec(None) is None


def test_valid_json_is_normalised_to_compact_string():
    out = validators.gwexplorer_valid_spec('[{"a": 1}, {"b": 2}]')
    # Re-serialised compactly (no spaces) and stable.
    assert out == '[{"a":1},{"b":2}]'


def test_non_string_structure_is_json_encoded():
    out = validators.gwexplorer_valid_spec([{"x": 2}])
    assert out == '[{"x":2}]'


def test_invalid_json_raises_invalid():
    with pytest.raises(tk.Invalid):
        validators.gwexplorer_valid_spec("{not valid json}")
