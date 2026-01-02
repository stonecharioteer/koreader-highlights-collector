from app import create_app


def test_index_route_renders():
    app = create_app()
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    # Smoke check: landing should render and include CTA buttons
    assert b"Configure Sources" in resp.data or b"Browse Books" in resp.data
