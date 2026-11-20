"""M4: the built UI is served at "/" with the session token; the M3 protections still apply. Fake data only."""
import importlib.util
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from merchant_notebook import sqlstore as SQ
from merchant_notebook.api.app import CSP, STATIC, TOKEN_PLACEHOLDER, create_app
from merchant_notebook.api.security import TOKEN_HEADER
from merchant_notebook.keys import StaticKeyProvider

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8765"
TOKEN = "test-token-not-a-real-secret"


@pytest.fixture
def client(tmp_path):
    key = StaticKeyProvider(os.urandom(32))
    app = create_app(lambda: SQ.SqliteMerchantStore(tmp_path / "m.db", key), token=TOKEN)
    with TestClient(app, base_url=BASE, raise_server_exceptions=False) as c:
        yield c


def asset_paths(html: str):
    return re.findall(r'(?:src|href)="(/assets/[^"]+)"', html)


def test_the_build_is_in_the_repo_and_keeps_one_token_placeholder():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert html.count(f'<meta name="mcn-token" content="{TOKEN_PLACEHOLDER}"') == 1
    assert len(asset_paths(html)) == 2


def test_the_page_is_the_built_ui_with_this_runs_token(client):
    r = client.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert f'<meta name="mcn-token" content="{TOKEN}"' in r.text
    assert TOKEN_PLACEHOLDER not in r.text and '<div id="root">' in r.text
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["x-content-type-options"] == "nosniff"


def test_each_run_serves_its_own_token():
    a = TestClient(create_app(lambda: None), base_url=BASE).get("/").text
    b = TestClient(create_app(lambda: None), base_url=BASE).get("/").text
    ta, tb = (re.search(r'mcn-token" content="([^"]+)"', t).group(1) for t in (a, b))
    assert ta != tb and TOKEN_PLACEHOLDER not in (ta, tb)


def test_assets_are_served_with_the_right_type(client):
    paths = asset_paths(client.get("/").text)
    types = {}
    for p in paths:
        r = client.get(p)
        assert r.status_code == 200 and len(r.content) > 100
        assert r.headers["content-security-policy"] == CSP
        types[p.rsplit(".", 1)[-1]] = r.headers["content-type"].split(";")[0]
    assert types == {"js": "text/javascript", "css": "text/css"}


@pytest.mark.parametrize("name", ["missing.js", "%2e%2e%2findex.html", "..%5Cindex.html", "index.html", ""])
def test_unknown_and_traversal_asset_requests_are_404(client, name):
    assert client.get(f"/assets/{name}").status_code == 404


def test_host_origin_and_token_still_apply(client):
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/assets/x.js", headers={"Host": "evil.example:8765"}).status_code == 400
    assert client.post("/", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/merchants").status_code == 401
    assert client.get("/api/merchants", headers={TOKEN_HEADER: TOKEN}).status_code == 200


def test_the_built_page_loads_nothing_from_the_internet():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    # the only non-asset link is the empty icon (data:,), which stops the browser asking for /favicon.ico
    assert not re.search(r'(?:src|href)="(?!/assets/|data:,")', html), "only local assets"
    assert 'href="data:,"' in html
    css = next((STATIC / "assets").glob("*.css")).read_text(encoding="utf-8")
    assert "http" not in css and "@import" not in css
    js = next((STATIC / "assets").glob("*.js")).read_text(encoding="utf-8")
    assert "localStorage" not in js and "sessionStorage" not in js
    assert not re.search(r"""(?:fetch|import|src\s*=)\s*\(?\s*["']https?://""", js)


def test_generated_layout_is_up_to_date():
    spec = importlib.util.spec_from_file_location("gen_layout", ROOT / "tools" / "gen_layout.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    current = (ROOT / "web" / "src" / "layout.generated.ts").read_text(encoding="utf-8")
    assert current.replace("\r\n", "\n") == mod.build(), "run: python tools/gen_layout.py"


# ------------------------------------------------------------------ guest mode (M18)
def test_the_page_carries_the_guest_flag_and_the_built_html_keeps_its_placeholder():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert html.count('<meta name="mcn-guest" content="__MCN_GUEST__"') == 1


def _guest_client(tmp_path, guest):
    from fastapi.testclient import TestClient
    from merchant_notebook import sqlstore as SQ
    from merchant_notebook.keys import StaticKeyProvider
    app = create_app(lambda: SQ.SqliteMerchantStore(tmp_path / "g.db", StaticKeyProvider(b"k" * 32)), token=TOKEN, guest=guest)
    return TestClient(app, base_url="http://127.0.0.1:8765", headers={"Origin": "http://127.0.0.1:8765", TOKEN_HEADER: TOKEN})


def test_guest_mode_shows_the_banner_flag_and_refuses_sensitive_values(tmp_path):
    with _guest_client(tmp_path, True) as c:
        assert 'name="mcn-guest" content="1"' in c.get("/").text
        mid = c.post("/api/merchants", json={"text": "Example Goods LLC; owner@example.com"}).json()["merchant_id"]
        v = c.get(f"/api/merchants/{mid}").json()["version"]
        ok = c.patch(f"/api/merchants/{mid}/fields/business_information.legal_business_name",
                     json={"expected_version": v, "action": "set", "value": "Example Goods Inc"})
        assert ok.status_code == 200
        bad = c.patch(f"/api/merchants/{mid}/fields/personal_information.owners[0].ssn",
                      json={"expected_version": ok.json()["version"], "action": "set", "value": "123456" + "789"})
        assert bad.status_code == 403 and "Mode tamu" in bad.json()["detail"] and "123456789" not in bad.text
        assert c.get(f"/api/merchants/{mid}").json()["record"]["personal_information"]["owners"][0]["ssn"]["value"] in (None, "")


def test_normal_mode_has_no_guest_flag_and_accepts_the_same_value(tmp_path):
    with _guest_client(tmp_path, False) as c:
        assert 'name="mcn-guest" content="0"' in c.get("/").text
        mid = c.post("/api/merchants", json={"text": "Example Goods LLC; owner@example.com"}).json()["merchant_id"]
        v = c.get(f"/api/merchants/{mid}").json()["version"]
        r = c.patch(f"/api/merchants/{mid}/fields/personal_information.owners[0].ssn",
                    json={"expected_version": v, "action": "set", "value": "123456" + "789"})
        assert r.status_code == 200
