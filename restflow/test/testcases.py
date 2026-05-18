from django.test import testcases

from restflow.test.client import AsyncAPIClient


class AsyncAPITransactionTestCase(testcases.TransactionTestCase):
    """Async-shaped TransactionTestCase wired up with AsyncAPIClient."""

    client_class = AsyncAPIClient


class AsyncAPITestCase(testcases.TestCase):
    """Async-shaped TestCase wired up with AsyncAPIClient."""

    client_class = AsyncAPIClient


class AsyncAPISimpleTestCase(testcases.SimpleTestCase):
    """Async-shaped SimpleTestCase wired up with AsyncAPIClient."""

    client_class = AsyncAPIClient


class AsyncAPILiveServerTestCase(testcases.LiveServerTestCase):
    """Async-shaped LiveServerTestCase wired up with AsyncAPIClient."""

    client_class = AsyncAPIClient
