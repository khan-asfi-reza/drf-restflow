import restflow
from restflow.authentication import (
    AccessToken,
    BaseAuthentication,
    BasicAuthentication,
    JWTAuthentication,
    RefreshToken,
    RemoteUserAuthentication,
    SessionAuthentication,
    TokenAuthentication,
    TokenError,
)
from restflow.authentication.views import (
    TokenBlacklistView,
    TokenObtainView,
    TokenRefreshView,
)
from restflow.responses import (
    NDJSONResponse,
    SSEResponse,
    StreamingJSONListResponse,
)
from restflow.serializers import HyperlinkedModelSerializer
from restflow.caching import (
    CACHE_MISSING,
    ArgsKeyField,
    AsyncIODispatcher,
    CachedWrapper,
    CacheKeyField,
    CacheRegister,
    CacheStatus,
    CeleryDispatcher,
    ConstantKeyField,
    DefaultKeyConstructor,
    Dispatcher,
    DjangoModelKeyField,
    DjangoQDispatcher,
    DjangoRqDispatcher,
    DramatiqDispatcher,
    DrfSerializerKeyField,
    InlineDispatcher,
    InlineKeyConstructor,
    InvalidationRule,
    KeyConstructor,
    QueryParamsKeyField,
    RequestValueKeyField,
    ThreadPoolDispatcher,
    cache_result,
    register_dispatcher,
    registered_dispatcher_names,
    set_response_cache_header,
)
from restflow.filters import (
    BooleanField,
    ChoiceField,
    DateField,
    DateTimeField,
    DecimalField,
    DurationField,
    Email,
    EmailField,
    Field,
    FilterSet,
    FloatField,
    InlineFilterSet,
    IntegerField,
    IPAddress,
    IPAddressField,
    ListField,
    MultipleChoiceField,
    OrderField,
    RelatedField,
    RestflowFilterBackend,
    StringField,
    TimeField,
)
from restflow.pagination import (
    BasePagination,
    CursorPagination,
    FastPageNumberPagination,
    LimitOffsetPagination,
    PageNumberPagination,
)
from restflow.permissions import (
    AND,
    NOT,
    OR,
    AllowAny,
    BasePermission,
    DjangoModelPermissions,
    DjangoModelPermissionsOrAnonReadOnly,
    DjangoObjectPermissions,
    IsAdminUser,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
)
from restflow.serializers import DecimalField as SerializerDecimalField
from restflow.serializers import Field as SerializerField
from restflow.serializers import (
    InlineSerializer,
    ModelSerializer,
    Serializer,
    SerializerFieldMap,
)
from restflow.serializers import (
    get_field_from_type as get_serializer_field_from_type,
)
from restflow.throttling import (
    AnonRateThrottle,
    BaseThrottle,
    ScopedRateThrottle,
    SimpleRateThrottle,
    UserRateThrottle,
)
from restflow.views import (
    APIView,
    ActionConfig,
    AsyncAPIView,
    AsyncCreateAPIView,
    AsyncCreateModelMixin,
    AsyncDestroyAPIView,
    AsyncDestroyModelMixin,
    AsyncGenericAPIView,
    AsyncGenericViewSet,
    AsyncListAPIView,
    AsyncListCreateAPIView,
    AsyncListModelMixin,
    AsyncModelViewSet,
    AsyncReadOnlyModelViewSet,
    AsyncRetrieveAPIView,
    AsyncRetrieveDestroyAPIView,
    AsyncRetrieveModelMixin,
    AsyncRetrieveUpdateAPIView,
    AsyncRetrieveUpdateDestroyAPIView,
    AsyncUpdateAPIView,
    AsyncUpdateModelMixin,
    AsyncViewSet,
    PostFetch,
)


def test_package_exposes_version_string():
    assert isinstance(restflow.__version__, str)
    assert restflow.__version__


def test_caching_public_api_imports_resolve_to_real_objects():
    names = [
        CACHE_MISSING, ArgsKeyField, AsyncIODispatcher, CacheKeyField,
        CacheRegister, CacheStatus, CachedWrapper, CeleryDispatcher,
        ConstantKeyField, DefaultKeyConstructor, Dispatcher, DjangoModelKeyField,
        DjangoQDispatcher, DjangoRqDispatcher, DramatiqDispatcher,
        DrfSerializerKeyField, InlineDispatcher, InlineKeyConstructor,
        InvalidationRule, KeyConstructor, QueryParamsKeyField,
        RequestValueKeyField, ThreadPoolDispatcher, cache_result,
        register_dispatcher, registered_dispatcher_names,
        set_response_cache_header,
    ]
    assert all(item is not None for item in names)


def test_filters_public_api_imports_resolve_to_real_objects():
    names = [
        BooleanField, ChoiceField, DateField, DateTimeField, DecimalField,
        DurationField, Email, EmailField, Field, FilterSet, FloatField,
        InlineFilterSet, IntegerField, IPAddress, IPAddressField, ListField,
        MultipleChoiceField, OrderField, RelatedField, RestflowFilterBackend,
        StringField, TimeField,
    ]
    assert all(item is not None for item in names)


def test_register_singleton_returns_same_instance():
    from restflow.caching.registry import CacheRegistry
    assert CacheRegistry() is CacheRegister


def test_cache_result_decorator_wraps_function_into_cached_wrapper():
    @cache_result(
        {"fields": {"v": ConstantKeyField("v", "1")}},
        ttl=60,
    )
    def hello(x):
        return x

    assert isinstance(hello, CachedWrapper)
    assert hello.is_cached_function is True
    assert hello.__name__ == "hello"


def test_filterset_instantiates_with_minimal_options():
    class _NoOpFilterSet(FilterSet):
        pass

    instance = _NoOpFilterSet(data={})
    assert hasattr(instance, "fields")


def test_serializers_public_api_imports_resolve_to_real_objects():
    names = [
        InlineSerializer,
        ModelSerializer,
        Serializer,
        SerializerDecimalField,
        SerializerField,
        SerializerFieldMap,
        get_serializer_field_from_type,
    ]
    assert all(item is not None for item in names)


def test_serializer_instantiates_with_annotations():
    class _Ser(Serializer):
        name: str
        age: int

    s = _Ser(data={"name": "x", "age": 1})
    assert s.is_valid()
    assert s.validated_data == {"name": "x", "age": 1}


def test_authentication_public_api_imports_resolve():
    names = [
        AccessToken, BaseAuthentication, BasicAuthentication,
        JWTAuthentication, RefreshToken, RemoteUserAuthentication,
        SessionAuthentication, TokenAuthentication, TokenBlacklistView,
        TokenError, TokenObtainView, TokenRefreshView,
    ]
    assert all(item is not None for item in names)


def test_responses_public_api_imports_resolve():
    names = [NDJSONResponse, SSEResponse, StreamingJSONListResponse]
    assert all(item is not None for item in names)


def test_hyperlinked_model_serializer_importable():
    assert HyperlinkedModelSerializer is not None


def test_permissions_public_api_imports_resolve():
    names = [
        AND, NOT, OR, AllowAny, BasePermission,
        DjangoModelPermissions, DjangoModelPermissionsOrAnonReadOnly,
        DjangoObjectPermissions, IsAdminUser, IsAuthenticated,
        IsAuthenticatedOrReadOnly,
    ]
    assert all(item is not None for item in names)


def test_throttling_public_api_imports_resolve():
    names = [
        AnonRateThrottle, BaseThrottle, ScopedRateThrottle,
        SimpleRateThrottle, UserRateThrottle,
    ]
    assert all(item is not None for item in names)


def test_pagination_public_api_imports_resolve():
    names = [
        BasePagination, CursorPagination, FastPageNumberPagination,
        LimitOffsetPagination, PageNumberPagination,
    ]
    assert all(item is not None for item in names)


def test_views_public_api_imports_resolve():
    names = [
        APIView, ActionConfig, AsyncAPIView, AsyncCreateAPIView,
        AsyncCreateModelMixin, AsyncDestroyAPIView, AsyncDestroyModelMixin,
        AsyncGenericAPIView, AsyncGenericViewSet, AsyncListAPIView,
        AsyncListCreateAPIView, AsyncListModelMixin, AsyncModelViewSet,
        AsyncReadOnlyModelViewSet, AsyncRetrieveAPIView,
        AsyncRetrieveDestroyAPIView, AsyncRetrieveModelMixin,
        AsyncRetrieveUpdateAPIView, AsyncRetrieveUpdateDestroyAPIView,
        AsyncUpdateAPIView, AsyncUpdateModelMixin, AsyncViewSet, PostFetch,
    ]
    assert all(item is not None for item in names)


def test_async_apiview_marks_subclass_as_async():
    class _MyView(AsyncAPIView):
        pass

    assert _MyView.view_is_async is True


def test_async_modelviewset_as_view_returns_coroutine_function():
    import inspect

    class _MyVS(AsyncModelViewSet):
        queryset = None
        serializer_class = None

    view = _MyVS.as_view({"get": "list"})
    assert inspect.iscoroutinefunction(view)


def test_registered_dispatcher_names_returns_builtins():
    names = registered_dispatcher_names()
    assert {
        "inline",
        "celery",
        "threadpool",
        "asyncio",
        "django_rq",
        "dramatiq",
        "django_q",
    }.issubset(set(names))
