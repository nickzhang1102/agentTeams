"""Transport boundary: user analysis is exposed only through Leader APIs."""


def test_application_exposes_no_legacy_chat_routes():
    from app import app
    from tests.conftest import iter_app_route_paths

    route_paths = set(iter_app_route_paths(app))

    assert not any(path == '/api/chat' or path.startswith('/api/chat/') for path in route_paths)
    assert '/api/leader/start' in route_paths
