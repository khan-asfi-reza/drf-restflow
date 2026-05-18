from typing import Literal

import pytest

from restflow.helpers import resolve_field_from_type


def test_resolve_literal_without_choice_field_class_raises():
    with pytest.raises(AssertionError, match="unsupported"):
        resolve_field_from_type(
            Literal["a", "b"],
            type_map={},
            choice_field_class=None,
        )


def test_resolve_list_without_list_field_class_raises():
    with pytest.raises(AssertionError, match="unsupported list"):
        resolve_field_from_type(
            list[str],
            type_map={},
            list_field_class=None,
        )


def test_resolve_field_from_type_handles_annotated():
    from typing import Annotated

    from rest_framework import fields as drf_fields

    from restflow.helpers import resolve_field_from_type

    field = resolve_field_from_type(
        Annotated[int, "label"],
        type_map={int: drf_fields.IntegerField},
    )
    assert isinstance(field, drf_fields.IntegerField)


def test_resolve_field_from_type_rejects_multi_arm_union():
    import pytest
    from rest_framework import fields as drf_fields

    from restflow.helpers import resolve_field_from_type

    with pytest.raises(AssertionError, match="multiple non-None members"):
        resolve_field_from_type(
            int | str,
            type_map={int: drf_fields.IntegerField, str: drf_fields.CharField},
        )


def test_resolve_field_from_type_rejects_optional_multi_arm():
    import pytest
    from rest_framework import fields as drf_fields

    from restflow.helpers import resolve_field_from_type

    with pytest.raises(AssertionError, match="multiple non-None members"):
        resolve_field_from_type(
            int | str | None,
            type_map={int: drf_fields.IntegerField, str: drf_fields.CharField},
        )
