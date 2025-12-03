from collections.abc import Callable
from typing import Any, Literal, Union, cast

from django.core.handlers.wsgi import WSGIRequest
from django.db.models import ForeignKey, Model, OneToOneField, Q, QuerySet
from django.db.models.constants import LOOKUP_SEP
from django.http import HttpRequest
from rest_framework import fields as drf_fields
from rest_framework.request import Request
from rest_framework.serializers import Serializer, SerializerMetaclass

from restflow.filters.fields import (
    LOOKUP_DEFAULT_FIELD,
    BooleanField,
    ChoiceField,
    DateField,
    DateTimeField,
    DecimalField,
    DurationField,
    EmailField,
    Field,
    FloatField,
    IntegerField,
    IPAddressField,
    ListField,
    OrderField,
    RelatedField,
    StringField,
    TimeField,
    extract_model_fields,
    get_field_from_type,
)

DJANGO_FIELD_MAP = {
    "CharField": StringField,
    "TextField": StringField,
    "EmailField": EmailField,
    "URLField": StringField,
    "SlugField": StringField,
    "IntegerField": IntegerField,
    "BigIntegerField": IntegerField,
    "SmallIntegerField": IntegerField,
    "PositiveIntegerField": IntegerField,
    "PositiveSmallIntegerField": IntegerField,
    "FloatField": FloatField,
    "DecimalField": DecimalField,
    "DateField": DateField,
    "DateTimeField": DateTimeField,
    "TimeField": TimeField,
    "DurationField": DurationField,
    "BooleanField": BooleanField,
    "IPAddressField": IPAddressField,
    "GenericIPAddressField": IPAddressField,
    "ForeignKey": IntegerField,
    "OneToOneField": IntegerField,
    "ArrayField": ListField,  # ArrayField (Postgres)
}

FieldItems = list[tuple[str, Field]]



def getattr_multi_source(obj_set: list[Any], attr_name: str, default=None) -> Any:
    """
    Gets attribute from the first object in obj_set that has it.
    Used for merging Meta options from multiple inheritance.
    """
    if not obj_set:
        obj_set = []

    if not isinstance(obj_set, (list, tuple)):
        obj_set = [obj_set]
    for obj in obj_set:
        if not obj:
            continue
        value = getattr(obj, attr_name, default)
        if value is not default:
            return value
    return default



class FilterOptions:
    """
    Attributes:
        model: The Django model to filter against.
        fields: Fields to include in the filterset.
        exclude: Fields to exclude from the filterset.
        extra_kwargs: Additional keyword arguments for field configuration.
        required_fields: Fields that should be marked as required.
        enable_ordering: Whether to disable automatic OrderField generation.
        order_param: Query parameter name for ordering.
        order_fields: Available ordering options.
        default_order_fields: Default ordering when none is specified.
        order_field_labels: Display labels for ordering options.
        override_order_dir: Override default ordering direction.
        postprocessors: Functions to run after filtering.
        preprocessors: Functions to run before filtering.
        operator: Logical operator for combining filters.
        allow_negate: Enables negation for fields (Only works for annotated fields and model fields).
    """

    def __init__(self, options: list[Any] | None):
        # Models and fields
        self.model: type[Model] = getattr_multi_source(options, "model", None)
        self.fields: Union[
            list[str],
            tuple[str],
            str,
        ] = getattr_multi_source(options, "fields", [])
        self.exclude: Union[list[str], tuple[str]] = getattr_multi_source(options, "exclude", [])

        self.extra_kwargs: dict[str, dict[str, Any]] = getattr_multi_source(options, "extra_kwargs", {})
        self.required_fields = getattr_multi_source(options, "required_fields", []) or []

        self.order_param: str = getattr_multi_source(options, "order_param", "order_by")
        self.order_fields: list[tuple[str, str]] = (
                getattr_multi_source(options, "order_fields", []) or []
        )
        self.default_order_fields: list[str] = (
                getattr_multi_source(options, "default_order_fields", []) or []
        )
        self.order_field_labels: list[tuple[str, str]] = (
                getattr_multi_source(options, "order_field_labels", []) or []
        )
        self.override_order_dir: Literal["asc", "desc"] = getattr_multi_source(
            options, "override_order_dir", "asc"
        )

        self.postprocessors: list[Callable[[FilterSet, QuerySet], Any]] = (
                getattr_multi_source(options, "postprocessors", []) or []
        )
        self.preprocessors: list[Callable[[FilterSet, QuerySet], Any]] = (
                getattr_multi_source(options, "preprocessors", []) or []
        )

        self.allow_negate = getattr_multi_source(options, "allow_negate", True)

        self.related_fields = getattr_multi_source(options, "related_fields", [])

        operator = getattr_multi_source(options, "operator", "AND")
        self.operator = (operator or "AND").upper()
        if self.operator not in ["AND", "OR", "XOR"]:
            msg = "Operator must be one of AND, OR, XOR"
            raise ValueError(msg)

        # Is used to determine whether to generate OrderField
        self.enable_ordering = bool(self.order_fields)


class FilterMetaClass(SerializerMetaclass):
    """
    Field generation priority: explicit declarations > type annotations > Meta.fields
    """

    def __new__(cls, name, bases: tuple[type[Any]], attrs: dict[str, Any]):
        # Instead of using class Meta, MetaOptions is used to store all options.
        # This way not all options need to be re-initiated.
        # Only the re-initiated option in the final class will be updated,
        # the rest will be inherited from base classes
        _options = [attrs.get("Meta")] + [getattr(base, "_meta", None) for base in bases]
        meta_options = FilterOptions(
            options=_options
        )
        # Restrict using Meta class directly in favor of FilterOptions
        attrs.pop("Meta", None)
        attrs["_meta"] = meta_options
        # Python 3.14>= attrs do not contain __annotations__
        # python3.14, annotations are handled lazily
        klass = type.__new__(cls, name, bases, attrs)
        declared_fields = cls._get_all_fields(klass, bases, attrs, meta_options)
        klass._declared_fields = declared_fields
        return klass

    @classmethod
    def _get_all_fields(
            cls, klass: type[Any], bases: tuple[type[Any]], attrs: dict[str, Any], options: FilterOptions
    ) -> dict[str, Field]:
        # Returns all declared fields, inherited fields
        # Also makes sure the order field is the last one
        base_fields = cls._get_base_fields(bases, attrs)
        user_fields = cls._get_user_defined_fields(
            klass=klass, attrs=attrs, options=options
        )
        order_field_config = cls._extract_order_field(user_fields, options)
        extended_fields = cls._generate_field_variants(user_fields,)
        all_fields = dict(base_fields + extended_fields)

        if order_field_config:
            cls._get_and_attach_order_field(all_fields, order_field_config)

        return all_fields

    @classmethod
    def _get_base_fields(cls, bases: tuple[type[Any]], attrs: dict[str, Any]) -> FieldItems:
        # Handle inherited fields, make sure the re-declared fields
        # are not fetched from parent classes
        known_attrs = set(attrs)

        def mark_as_known(name):
            known_attrs.add(name)
            return name

        return [
            (mark_as_known(name), field)
            for base in bases
            if hasattr(base, "_declared_fields")
            for name, field in getattr(base, "_declared_fields", {}).items()
            if name not in known_attrs
        ]

    @classmethod
    def _get_user_defined_fields(
            cls, klass: type[Any], attrs: dict[str, Any], options: FilterOptions
    ) -> FieldItems:
        # Field generation priority (which source wins for the same field name)
        #   explicit declarations > annotations > Meta.fields
        #
        # Output order (position in fields dict):
        #   annotations appear first, then explicit, then model fields
        #   Note: Cannot preserve exact declaration order for annotated fields
        #   due to Python's annotation handling

        explicit_fields = cls._get_explicit_fields(klass, options, attrs)
        explicit_names = {name for name, _ in explicit_fields}

        annotated_fields = cls._build_fields_from_annotations(
            klass, explicit_names, options
        )
        annotated_names = {name for name, _ in annotated_fields}

        for field_name, field in explicit_fields + annotated_fields:
            field.ensure_db_field(field_name)

        model_fields = cls._generate_model_fields(
            options, annotated_names | explicit_names
        )
        return annotated_fields + explicit_fields + model_fields

    @classmethod
    def _get_explicit_fields(cls, klass, options, attrs: dict[str, Any], ) -> FieldItems:
        # Explicit field declaration and FilterSet declarations
        annotations = getattr(klass, "__annotations__", {})
        fields = [
            (field_name, attrs.pop(field_name))
            for field_name, obj in list(attrs.items())
            if isinstance(obj, drf_fields.Field) and not isinstance(obj, FilterSet)
               and not (obj.__class__ is Field and field_name in annotations)
        ]
        fields.sort(key=lambda x: getattr(x[1], "_creation_counter", 0))
        return cls._extract_related_fields(fields, options)

    @classmethod
    def _extract_related_fields(cls, fields: FieldItems, options: FilterOptions) -> FieldItems:
        # Expand RelatedField instances into their constituent fields.
        expanded = []

        for field_name, field in fields:
            if isinstance(field, RelatedField):
                # Expand this RelatedField
                model_fields = field.get_model_fields()
                filter_fields = cls._extract_django_model_fields(
                    model_fields=model_fields,
                    options=options,
                    exclude_fields=set(field.negate or []),
                    extra_kwargs=field.extra_kwargs,
                    field_name_prefix=field_name
                )
                expanded.extend(filter_fields)
            else:
                expanded.append((field_name, field))

        return expanded

    @classmethod
    def _build_fields_from_annotations(
            cls, klass: type[Any], existing_fields: set, options: FilterOptions
    ) -> FieldItems:
        # Gets the fields that have annotation
        # It will either create respective data type oriented Field
        # Or it will clone the field with the appropriate type and field_name
        annotated_fields = getattr(klass, "__annotations__", {})
        annotated = []
        for field_name, field_type in annotated_fields.items():
            if field_name in existing_fields:
                continue
            field = getattr(klass, field_name, None)
            # For annotations with following
            # eg: field1: int = Field(...)
            # it will build the field
            # with the appropriate type by passing arguments of the declared field into the generated field.
            if field and field.__class__ is Field:
                annotated.append((field_name, field.clone(
                    _type=field_type,
                    field_name=field_name,
                )))
                continue

            default_kwargs = {"allow_negate": options.allow_negate, "db_field": field_name}
            default_kwargs.update(options.extra_kwargs.get(field_name, {}))
            field_obj = get_field_from_type(
                field_type,
                field_name=field_name,
                **default_kwargs
            )
            annotated.append((field_name, field_obj))
        return annotated

    @classmethod
    def _generate_model_fields(cls, options: FilterOptions, existing_names: set[str]) -> FieldItems:
        # Generate fields from a Django model if Meta.fields is configured as `__all__` or a list of field names
        if not options or options.model is None:
            return []

        model_fields = extract_model_fields(
            model=options.model,
            fields=options.fields,
            exclude=options.exclude
        )

        return cls._extract_django_model_fields(
            model_fields=model_fields,
            options=options,
            extra_kwargs=options.extra_kwargs,
            exclude_fields=existing_names
        )

    @classmethod
    def _extract_django_model_fields(
            cls,
            model_fields: list[Any],
            options: FilterOptions,
            extra_kwargs: dict[str, dict[str, Any]],
            exclude_fields: set[str] | None=None,
            field_name_prefix: str | None=None
    ) -> FieldItems:
        # Extracts fields from django fields, creates appropriate FilterField objects
        fields = []
        exclude_fields = exclude_fields or set()
        handled_fields = set()

        for django_field in model_fields:
            field_name = django_field.name

            # To avoid recursive field generation for RelatedFields
            if field_name in handled_fields | exclude_fields:
                continue

            # Skip reverse relations by default
            if hasattr(django_field, "related_model") and django_field.one_to_many:
                continue

            field_type = django_field.__class__.__name__
            field_class = DJANGO_FIELD_MAP.get(field_type, StringField)
            field_kwargs = extra_kwargs.get(field_name, {})

            kwargs = {}
            kwargs.setdefault("filter_by", f"{django_field.name}")
            kwargs.setdefault("db_field", f"{django_field.name}")
            kwargs.setdefault("lookups", [])

            if isinstance(django_field, (ForeignKey, OneToOneField)):
                # For relations, use the related field's ID
                kwargs["filter_by"] = f"{django_field.name}__pk"
                if field_name in options.related_fields:
                    related_fields = cls._extract_django_model_fields(
                        model_fields=django_field.related_model._meta.get_fields(),
                        options=options,
                        extra_kwargs=extra_kwargs,
                        field_name_prefix=field_name,
                        exclude_fields=field_kwargs.get("exclude") or set()
                    )
                    fields.extend(related_fields)
                    continue

            elif hasattr(django_field, "choices") and django_field.choices:
                field_class = ChoiceField
                kwargs["choices"] = django_field.choices

            elif field_type == "ArrayField": # Postgres ArrayField
                kwargs["lookups"] = ["pg_array"]
                base_field = django_field.base_field.__class__.__name__
                kwargs["child"] = DJANGO_FIELD_MAP.get(base_field, StringField)()

            kwargs.update(field_kwargs)
            filter_field = field_class(**kwargs)
            if field_name_prefix:
                field_name = f"{field_name_prefix}__{field_name}"

            fields.append((field_name, filter_field))
            handled_fields.add(field_name)

        return fields

    @classmethod
    def _extract_order_field(cls, fields: FieldItems, options: FilterOptions) -> tuple[str, Field] | None:
        # Gets the order field or sets order fields from the options
        # Note: this will temporarily remove the order field from the field list
        # Later to be added via _get_and_attach_order_field()
        order_fields = [
            (idx, name, field)
            for idx, (name, field) in enumerate(fields)
            if isinstance(field, OrderField)
        ]

        if len(order_fields) > 1:
            msg = f"Only one order field is allowed, found multiple: {', '.join(name for _, name, _ in order_fields)}"
            raise ValueError(msg)

        if order_fields:
            idx, name, field = order_fields[0]
            fields.pop(idx)
            return name, field

        if options and options.enable_ordering:
            field = OrderField(
                labels=options.order_field_labels,
                default=options.default_order_fields,
                fields=options.order_fields,
                override_order_dir=options.override_order_dir,
            )

            return options.order_param, field

        return None

    @classmethod
    def _generate_field_variants(cls, base_fields: FieldItems, ) -> FieldItems:
        # Generate all possible / provided field variants
        # Negate fields for provided fields and lookup fields
        field_order = {name: idx for idx, (name, _) in enumerate(base_fields)}
        all_variants = list(base_fields)

        for field_name, field in base_fields:
            all_variants.extend(cls._create_lookup_variants(field_name, field))

        negated_fields = []

        for field_name, field in all_variants:
            negated_fields.extend(cls._create_negation_variant(field_name, field))

        all_variants.extend(negated_fields)
        cls._sort_by_base_field_order(all_variants, field_order)
        return all_variants


    @classmethod
    def _create_lookup_variants(cls, field_name: str, field: Field) -> FieldItems:
        # Create additional fields for each lookup type (e.g., field__gte, field__lte)
        if field.method or callable(field.filter_by):
            return []


        lookups = getattr(field, "lookups", []) or []
        variants = []

        lookup_fields = list(lookups.keys()) if isinstance(lookups, dict) else lookups

        for lookup in lookup_fields:
            variant_name = f"{field_name}{LOOKUP_SEP}{lookup}"
            variant_expr = f"{field.db_field}{LOOKUP_SEP}{lookup}"
            field_kwargs = {
                "filter_by": variant_expr,
                "lookups": []
            }

            field_class = LOOKUP_DEFAULT_FIELD.get(lookup)
            cloned_class = field.clone(**field_kwargs)

            if field_class and field_class == ListField:
                field_kwargs["child"] = cloned_class

            lookup_field = field_class(**field_kwargs) if field_class else cloned_class
            variants.append((variant_name, lookup_field))

        return variants

    @classmethod
    def _create_negation_variant(cls, field_name: str, field: Field,) -> FieldItems:
        if field.allow_negate:
            negation_name = f"{field_name}!"
            return [(negation_name, field.clone(negate=True))]
        return []


    @classmethod
    def _sort_by_base_field_order(cls, fields:FieldItems, order_map):
        # This will make sure all the fields are ordered based on their declaration
        # For variants, it will rely on their parent field's order
        def get_base_name(field_name):
            return field_name.split(LOOKUP_SEP)[0].split("!")[0]
        fields.sort(key=lambda x: order_map.get(get_base_name(x[0]), 0))

    @classmethod
    def _get_and_attach_order_field(cls, field_dict, order_config):
        # Add OrderField to the end of the field dictionary, removing any inherited ones.
        # Order field should be at the end
        # Also remove any inherited order fields
        name, field = order_config
        inherited_order_fields = [
            field_name
            for field_name, field_obj in field_dict.items()
            if isinstance(field_obj, OrderField)
        ]

        for inherited_name in inherited_order_fields:
            field_dict.pop(inherited_name)

        field_dict[name] = field
        return name



class FilterSet(Serializer, metaclass=FilterMetaClass):
    """
    A declarative way to filter Django `querysets`.

    FilterSet extends rest_framework.serializers.Serializer to provide query parameter validation and queryset
    filtering. It supports type annotations, explicit field declarations, and automatic
    field generation from Django models.

    Attributes:
        request (Request): The DRF request object containing query parameters.

    Meta Configuration:
        model (Model): Django model to filter. Required when using Meta.fields.

        fields (Union[List[str], Tuple[str], Literal["__all__"]]): Fields to include.
            Use "__all__" to include all model fields or provide a list of field names.
            Explicitly declared fields take precedence over this setting.

        exclude (Union[List[str], Tuple[str]]): Fields to exclude when using "__all__".

        extra_kwargs (Dict[str, Dict]): Additional keyword arguments for fields.

        required_fields (List[str]): Field names that should be marked as required.

        order_param (str): Query parameter name for ordering. The default is "order_by".

        order_fields (List[Tuple[str, str]]): Available ordering options as
            (query_value, model_field) tuples.

        default_order_fields (List[str]): Default ordering when no order param is provided.

        order_field_labels (List[Tuple[str, str]]): Human-readable labels for ordering
            options as (query_value, label) tuples.

        override_order_dir (Literal["asc", "desc"]): Override Django's default ordering
            direction. Use "desc" to reverse the meaning of the "-" prefix. The default is "asc".

        preprocessors (List[Callable[[FilterSet, QuerySet], QuerySet]]): Functions called
            before filtering. Each receives the filterset and queryset, returns queryset.

        postprocessors (List[Callable[[FilterSet, QuerySet], QuerySet]]): Functions called
            after filtering. Each receives the filterset and queryset, returns queryset.

        operator (Literal["AND", "OR", "XOR"]): Logical operator for combining filters.
            Default is "AND".

        allow_negate (bool): Enables negation for fields (Only works for annotated fields and model fields).

    Methods:
        model_dump() -> dict:
            Validates and returns cleaned query parameters as a dictionary.

        filter_queryset(queryset: QuerySet) -> QuerySet:
            Applies validated filters to the queryset and returns filtered results.

    Examples:
        Using type annotations::

            class ProductFilterSet(FilterSet):
                name: str
                price: int
                in_stock: bool

        Using explicit field declarations::

            from restflow.fields import StringField, IntegerField

            class ProductFilterSet(FilterSet):
                name = StringField(lookups=["icontains"])
                price = IntegerField(lookups=["gte", "lte"])
                category = StringField(filter_by="category__name")

        Using a Django model with Meta:

            class ProductFilterSet(FilterSet):
                class Meta:
                    model = Product
                    fields = "__all__"
                    order_fields = [("price", "price"), ("name", "name")]

        In a view::

            def list_products(request):
                queryset = Product.objects.all()
                filterset = ProductFilterSet(request=request)
                filtered_queryset = filterset.filter_queryset(queryset)
                return Response (data=list(filtered_queryset.values()))

    Note:
        - Fields automatically generate negation variants (e.g., "price!" for not equal), allow_negate=True.
        - Lookup fields are generated from the lookups parameter (e.g., "price__gte")
        - Field priority: explicit declarations > type annotations > Meta.fields
    """

    def __init__(
            self,
            data=None,
            request: Request | WSGIRequest | HttpRequest = None,
    ):
        self.request = request
        # Flexibility for users
        if data is None and request:
            data = getattr(request, "query_params", {}) or getattr(request, "GET", {})
        super().__init__(
            data=data,
            context={
                "request": request
            }
        )

    def get_options(self):
        return getattr(self, "_meta", None)

    def many_init(self):
        msg = "`many=True` is not supported."
        raise NotImplementedError(msg)

    def model_dump(self):
        """
        Validate query parameters and return cleaned data as a dictionary.

        Returns:
            dict: Dictionary of validated query parameters.

        Raises:
            ValidationError: If validation fails.

        """
        self.is_valid(raise_exception=True)
        return self.validated_data

    def _apply_processors(
            self, queryset: QuerySet, processor_type: Literal["pre", "post"]
    ):
        # Runs preprocessors or postprocessors on the queryset
        options = self.get_options()
        processors = getattr(options, f"{processor_type}processors", [])
        for processor in processors:
            queryset = processor(self, queryset)
        return queryset

    def filter_queryset(
            self,
            queryset: QuerySet,
            ignore=None,
    ):
        """
        Apply validated filters to a queryset and return the filtered result.

        Args:
            queryset (QuerySet): The Django queryset to filter.
            ignore (list[str], optional): List of field names to ignore. Defaults to None.
        Returns:
            QuerySet: The filtered queryset after applying all filters and processors.

        Raises:
            ValidationError: If query parameters fail validation.

        """
        options = self.get_options()
        validated_data = self.model_dump()
        queryset = self._apply_processors(queryset, "pre")
        ignore = ignore or []

        q_objects = []
        for field_name, value in validated_data.items():
            field = self.fields.get(field_name)
            if field is None or field_name in ignore:
                continue    # pragma: no cover
            result = field.apply_filter(
                filterset=self, queryset=queryset, value=value
            )

            # Handle both tuple and single return values
            if isinstance(result, tuple):
                queryset, q_obj = result
            else:
                q_obj = result

            if isinstance(q_obj, Q):
                q_objects.append(q_obj)

            elif isinstance(q_obj, QuerySet):
                queryset = q_obj

        if q_objects:
            operator = options.operator
            combined_q = q_objects[0]

            for q_obj in q_objects[1:]:
                if operator == "OR":
                    combined_q |= q_obj
                elif operator == "XOR":
                    combined_q ^= q_obj
                else:  # AND
                    combined_q &= q_obj
            queryset = queryset.filter(combined_q)

        return self._apply_processors(queryset, "post")


class InlineFilterSet:
    """
    Create a FilterSet class dynamically without defining a class explicitly.
    This factory function generates a FilterSet class on-the-fly, useful for creating
    simple filtersets without the boilerplate of class definitions.
    """
    def __new__(
            cls,
            name: str | None = None,
            fields: dict[str, Union[Field, type]] | None = None,
            extra_kwargs: dict[str, dict] | None = None,
            model: type[Model] | None = None,
            order_param: str = "",
            order_fields: list[tuple[str, str]] | None = None,
            default_order_fields: list[str] | None = None,
            order_field_labels: list[tuple[str, str]] | None = None,
            override_order_dir: Literal["asc", "desc"] | None = None,
            postprocessors: list[Callable[[FilterSet, QuerySet], Any]] | None = None,
            preprocessors: list[Callable[[FilterSet, QuerySet], Any]] | None = None,
            operator: Literal["AND", "OR", "XOR"] = "AND",
            allow_negate:bool = True,
    ) -> type[FilterSet]:
        """
        Create a FilterSet class dynamically without defining a class explicitly.

        This factory function generates a FilterSet class on-the-fly, useful for creating
        simple filtersets without the boilerplate of class definitions.

        Args:
            name: Class name for the generated FilterSet.
            fields: Dictionary mapping field names to Field instances or type annotations.
            extra_kwargs: Additional keyword arguments to pass to generated fields.
            model: Django model to associate with the FilterSet.
            order_param: Query parameter name for ordering. The default is "order_by".
            order_fields: List of (query_value, model_field) tuples for ordering options.
            default_order_fields: Default ordering fields to apply.
            order_field_labels: List of (query_value, label) tuples for display.
            override_order_dir: Override ordering direction ("asc" or "desc").
            postprocessors: Functions to run after filtering.
            preprocessors: Functions to run before filtering.
            operator: Logical operator for combining filters ("AND", "OR", or "XOR").
            allow_negate: Enables negation for fields (Only works for annotated fields and model fields).

        Returns:
            Type[FilterSet]: A dynamically created FilterSet class.

        Example:
             >>> from restflow.filters.fields import IntegerField, StringField
             >>> ProductFilter = InlineFilterSet(name="ProductFilter", model=Product) # noqa
             >>> filterset = ProductFilter(request=request) # noqa
        """

        attrs = {}

        MetaConfig = {
            "model": model,
            "extra_kwargs": extra_kwargs or {},
            "order_param": order_param,
            "order_fields": order_fields,
            "default_order_fields": default_order_fields,
            "order_field_labels": order_field_labels,
            "override_order_dir": override_order_dir,
            "postprocessors": postprocessors,
            "preprocessors": preprocessors,
            "operator": operator,
            "allow_negate": allow_negate,
        }

        if not (model or fields):
            msg = "Either `model` or `fields` must be provided."
            raise ValueError(msg)

        if model:
            name = name if name else f"{model.__name__}FilterSet"
            MetaConfig["fields"] = (
                "__all__"
                if not fields
                else fields if isinstance(fields, list | tuple) else []
            )

        if isinstance(fields, dict):
            for field_name, field in fields.items():
                if isinstance(field, Field):
                    attrs[field_name] = field
                else:
                    attrs[field_name] = get_field_from_type(field, field_name=field_name)

        name = name if name else "_FilterSet"

        attrs["Meta"] = type(
            "Meta",
            (),
            MetaConfig,
        )
        klass = type(name, (FilterSet,), attrs)
        return cast(type[FilterSet], klass)
