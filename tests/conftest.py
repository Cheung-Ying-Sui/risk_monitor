import pytest


@pytest.fixture(autouse=True)
def override_api_auth_for_non_auth_tests(request):
    if "test_api_auth.py" in request.node.nodeid:
        yield
        return

    from api.auth import get_authenticated_user
    from api.main import app

    app.dependency_overrides[get_authenticated_user] = lambda: {"id": "test-user"}
    yield
    app.dependency_overrides.pop(get_authenticated_user, None)
