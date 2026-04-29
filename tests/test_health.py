"""Tests de healthcheck para SIIF (08-siif)."""
import os
import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLASK_ENV", "testing")


@pytest.fixture
def client():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from app import create_app
    app = create_app("development")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_health_standard_route(client):
    """GET /api/health debe retornar 200 sin autenticación."""
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "siif"


def test_health_compat_route(client):
    """GET /health también debe retornar 200."""
    r = client.get("/health")
    assert r.status_code == 200


def test_login_page_loads(client):
    """GET /login debe cargar el formulario."""
    r = client.get("/login")
    assert r.status_code == 200


def test_protected_route_redirects(client):
    """GET / sin sesión debe redirigir al login."""
    r = client.get("/")
    assert r.status_code in (302, 401)
