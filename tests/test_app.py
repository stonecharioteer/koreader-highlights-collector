from app import create_app


def test_index_route_renders():
    app = create_app()
    client = app.test_client()
    resp = client.get('/')
    assert resp.status_code == 200
    # Basic smoke check on content
    assert b'Books' in resp.data

