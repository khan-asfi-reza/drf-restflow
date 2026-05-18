import pytest


@pytest.fixture(autouse=True)
def _clear_register():
    from restflow.caching import CacheRegister

    CacheRegister.clear()
    yield
    CacheRegister.clear()
