from restflow.filters import OrderField


def _field():
    return OrderField(
        fields=[("id", "id"), ("price", "price"), ("name", "name")],
        labels=[("price", "Price")],
    )


def test_partial_labels_keep_every_declared_option():
    assert set(_field().choices) == {
        "id",
        "-id",
        "price",
        "-price",
        "name",
        "-name",
    }


def test_unlabelled_options_fall_back_to_the_option_key():
    labels = dict(_field().choices)
    assert labels["price"] == "Price (Ascending)"
    assert labels["id"] == "id (Ascending)"
    assert labels["-name"] == "name (Descending)"


def test_partial_labels_still_validate_unlabelled_values():
    assert _field().to_internal_value("id,-price") == ["id", "-price"]


def test_omitted_labels_use_the_model_field_text():
    field = OrderField(fields=[("price", "price")])
    assert dict(field.choices)["price"] == "price (Ascending)"


def test_ordering_precedence_follows_the_request():
    field = OrderField(
        fields=[("name", "name"), ("price", "price"), ("id", "id")]
    )
    assert field.to_internal_value("name,-price") == ["name", "-price"]
    assert field.to_internal_value("-price,name") == ["-price", "name"]
    assert field.to_internal_value(["id", "name,-price"]) == [
        "id",
        "name",
        "-price",
    ]


def test_ordering_values_are_deduplicated():
    field = OrderField(fields=[("name", "name"), ("price", "price")])
    assert field.to_internal_value("name,name,-price") == ["name", "-price"]
