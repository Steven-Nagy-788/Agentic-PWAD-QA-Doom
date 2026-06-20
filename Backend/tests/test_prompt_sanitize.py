from __future__ import annotations

import pytest

from app.services.prompt_service import _sanitize_prompt_value


def test_sanitize_json_string_with_braces_replaced() -> None:
    value = '{"key": "value", "count": 3}'
    result = _sanitize_prompt_value(value)
    assert result == '("key": "value", "count": 3)'


def test_sanitize_nested_json_replaced() -> None:
    value = '{"outer": {"inner": "data"}}'
    result = _sanitize_prompt_value(value)
    assert result == '("outer": ("inner": "data"))'


def test_sanitize_empty_json_object_replaced() -> None:
    value = '{}'
    result = _sanitize_prompt_value(value)
    assert result == '()'


def test_sanitize_json_array_preserved() -> None:
    value = '[1, 2, 3]'
    result = _sanitize_prompt_value(value)
    assert result == '[1, 2, 3]'


def test_sanitize_regular_string_preserved() -> None:
    value = 'Hello World'
    result = _sanitize_prompt_value(value)
    assert result == 'Hello World'


def test_sanitize_integer_converted_to_string() -> None:
    value = 42
    result = _sanitize_prompt_value(value)
    assert result == '42'
    assert isinstance(result, str)


def test_sanitize_float_converted_to_string() -> None:
    value = 3.14
    result = _sanitize_prompt_value(value)
    assert result == '3.14'


def test_sanitize_none_converted_to_string() -> None:
    value = None
    result = _sanitize_prompt_value(value)
    assert result == 'None'


def test_sanitize_bool_converted_to_string() -> None:
    value = True
    result = _sanitize_prompt_value(value)
    assert result == 'True'


def test_sanitize_string_without_braces_preserved() -> None:
    value = 'no braces here'
    result = _sanitize_prompt_value(value)
    assert result == 'no braces here'


def test_sanitize_partial_json_replaced() -> None:
    value = '{"incomplete":'
    result = _sanitize_prompt_value(value)
    assert result == '("incomplete":'


def test_sanitize_json_with_special_chars_replaced() -> None:
    value = '{"key": "value with spaces & symbols!"}'
    result = _sanitize_prompt_value(value)
    assert result == '("key": "value with spaces & symbols!")'


def test_sanitize_list_converted_to_string() -> None:
    value = ["a", "b", "c"]
    result = _sanitize_prompt_value(value)
    assert result == "['a', 'b', 'c']"


def test_sanitize_dict_converted_to_string() -> None:
    value = {"a": 1, "b": 2}
    result = _sanitize_prompt_value(value)
    assert result == "('a': 1, 'b': 2)"
