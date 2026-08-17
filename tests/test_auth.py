"""Supabase JWT 鉴权测试：ES256（JWKS）/ HS256 回退 / 全局中间件。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest

from value_agent.core import auth


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _claims(**over):
    claims = {
        "sub": "user-123",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
        "iss": "https://testref.supabase.co/auth/v1",
    }
    claims.update(over)
    return claims


@pytest.fixture
def es256_env(monkeypatch):
    """生成 P-256 密钥对，把公钥伪装成 JWKS，并指向测试项目 ref。"""
    import ecdsa

    monkeypatch.setenv("SUPABASE_URL", "https://testref.supabase.co")
    sk = ecdsa.SigningKey.generate(curve=ecdsa.NIST256p)
    vk = sk.get_verifying_key()
    pub = {
        "kty": "EC",
        "crv": "P-256",
        "kid": "test-kid",
        "x": _b64url(vk.pubkey.point.x().to_bytes(32, "big")),
        "y": _b64url(vk.pubkey.point.y().to_bytes(32, "big")),
        "alg": "ES256",
        "use": "sig",
    }
    monkeypatch.setattr(auth, "_fetch_jwks", lambda: {"keys": [pub]})
    return sk, pub


def _es256_token(sk, payload, kid="test-kid"):
    import ecdsa

    header = {"alg": "ES256", "typ": "JWT", "kid": kid}
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = sk.sign(f"{h}.{p}".encode(), hashfunc=hashlib.sha256, sigencode=ecdsa.util.sigencode_string)
    return f"{h}.{p}.{_b64url(sig)}"


def test_verify_es256_ok(es256_env):
    sk, _ = es256_env
    claims = auth.verify_supabase_jwt(_es256_token(sk, _claims()))
    assert claims["sub"] == "user-123"


def test_verify_rejects_expired(es256_env):
    sk, _ = es256_env
    with pytest.raises(ValueError, match="已过期"):
        auth.verify_supabase_jwt(_es256_token(sk, _claims(exp=int(time.time()) - 10)))


def test_verify_rejects_wrong_aud(es256_env):
    sk, _ = es256_env
    with pytest.raises(ValueError, match="aud"):
        auth.verify_supabase_jwt(_es256_token(sk, _claims(aud="anon")))


def test_verify_rejects_tampered_payload(es256_env):
    sk, _ = es256_env
    head, _, sig = _es256_token(sk, _claims()).split(".")
    bad = _b64url(json.dumps({**_claims(), "sub": "attacker"}, separators=(",", ":")).encode())
    with pytest.raises(ValueError, match="签名校验失败"):
        auth.verify_supabase_jwt(f"{head}.{bad}.{sig}")


def test_verify_hs256_fallback(monkeypatch):
    """轮换前老 token（HS256）用 SUPABASE_JWT_SECRET 回退验签。"""
    secret = "legacy-shared-secret"
    monkeypatch.setenv("SUPABASE_URL", "https://testref.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", secret)
    h = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    p = _b64url(json.dumps(_claims(), separators=(",", ":")).encode())
    si = f"{h}.{p}"
    sig = hmac.new(secret.encode(), si.encode(), hashlib.sha256).digest()
    claims = auth.verify_supabase_jwt(f"{h}.{p}.{_b64url(sig)}")
    assert claims["sub"] == "user-123"


def test_verify_no_secret_rejects_hs256(monkeypatch):
    """没配 SUPABASE_JWT_SECRET 时，HS256 老 token 拒绝（不降级为不校验）。"""
    monkeypatch.setenv("SUPABASE_URL", "https://testref.supabase.co")
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    h = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    p = _b64url(json.dumps(_claims(), separators=(",", ":")).encode())
    si = f"{h}.{p}"
    sig = hmac.new(b"whatever", si.encode(), hashlib.sha256).digest()
    with pytest.raises(ValueError, match="签名校验失败"):
        auth.verify_supabase_jwt(f"{h}.{p}.{_b64url(sig)}")


def test_middleware_requires_frontend_token(es256_env, monkeypatch):
    """全局中间件：/api/* 无 token → 401，带有效 Supabase JWT → 200；/health 不鉴权。"""
    import os

    os.environ["SESSION_STORE"] = "memory"
    os.environ["DATABASE_URL"] = ""

    from fastapi.testclient import TestClient

    from value_agent.main import app

    client = TestClient(app)

    r = client.get("/api/agents")
    assert r.status_code == 401

    sk, _ = es256_env
    r = client.get(
        "/api/agents",
        headers={"Authorization": f"Bearer {_es256_token(sk, _claims())}"},
    )
    assert r.status_code == 200

    # /health 探活不鉴权
    assert client.get("/health").status_code == 200

    # 无效 token → 401
    r = client.get("/api/agents", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_session_ownership_read(es256_env, monkeypatch):
    """会话归属校验：登录用户只能读/删自己的会话，列表只返回自己的会话。"""
    import os

    os.environ["SESSION_STORE"] = "memory"
    os.environ["DATABASE_URL"] = ""

    from fastapi.testclient import TestClient

    from value_agent.main import _manager, app

    session = _manager.create_session("600519", "贵州茅台", user_id="user-123")
    sid = session.id

    client = TestClient(app)
    sk, _ = es256_env

    def auth(sub: str):
        return {"Authorization": f"Bearer {_es256_token(sk, _claims(sub=sub))}"}

    # 本人可读
    r = client.get(f"/api/sessions/{sid}", headers=auth("user-123"))
    assert r.status_code == 200
    assert r.json()["id"] == sid

    # 他人读 → 404（不暴露会话存在）
    r = client.get(f"/api/sessions/{sid}", headers=auth("user-456"))
    assert r.status_code == 404

    # 列表只含本人会话
    ids_own = [x["id"] for x in client.get("/api/sessions", headers=auth("user-123")).json()["sessions"]]
    assert sid in ids_own
    ids_other = [x["id"] for x in client.get("/api/sessions", headers=auth("user-456")).json()["sessions"]]
    assert sid not in ids_other

    # 他人删除 → 404，本人删除 → 200
    r = client.delete(f"/api/sessions/{sid}", headers=auth("user-456"))
    assert r.status_code == 404
    r = client.delete(f"/api/sessions/{sid}", headers=auth("user-123"))
    assert r.status_code == 200


# ---- 静态 JWKS 注入 / 网络失败回退（FC 大陆出口访问 supabase.co 握手超时场景） ----

@pytest.fixture
def jwks_env_no_patch(monkeypatch):
    """生成 P-256 密钥对 + 公钥 JWKS 字典，设置 SUPABASE_URL，但不替换 _fetch_jwks。"""
    import ecdsa

    monkeypatch.setenv("SUPABASE_URL", "https://testref.supabase.co")
    sk = ecdsa.SigningKey.generate(curve=ecdsa.NIST256p)
    vk = sk.get_verifying_key()
    pub = {
        "kty": "EC",
        "crv": "P-256",
        "kid": "test-kid",
        "x": _b64url(vk.pubkey.point.x().to_bytes(32, "big")),
        "y": _b64url(vk.pubkey.point.y().to_bytes(32, "big")),
        "alg": "ES256",
        "use": "sig",
    }
    # 隔离：每个用例清空模块级内存缓存，避免跨用例命中
    monkeypatch.setattr(auth, "_jwks_cache", {"fetched_at": 0.0, "data": None})
    return sk, pub


def test_verify_es256_with_static_jwks_env(jwks_env_no_patch, monkeypatch):
    """SUPABASE_JWKS 环境变量注入 JWKS → 完全不走网络即可验签（FC 主解）。"""
    sk, pub = jwks_env_no_patch
    monkeypatch.setenv("SUPABASE_JWKS", json.dumps({"keys": [pub]}))

    class _BlockNetwork:
        @staticmethod
        def get(*args, **kwargs):  # 触发即失败：静态注入模式下不允许出网
            raise AssertionError("静态 JWKS 模式下不应发起网络请求")

    monkeypatch.setattr(auth, "httpx", _BlockNetwork)
    claims = auth.verify_supabase_jwt(_es256_token(sk, _claims()))
    assert claims["sub"] == "user-123"


def test_verify_es256_with_static_jwks_file(jwks_env_no_patch, monkeypatch, tmp_path):
    """SUPABASE_JWKS_FILE 指向文件注入 JWKS → 不走网络即可验签。"""
    sk, pub = jwks_env_no_patch
    jwks_file = tmp_path / "jwks.json"
    jwks_file.write_text(json.dumps({"keys": [pub]}), encoding="utf-8")
    monkeypatch.setenv("SUPABASE_JWKS_FILE", str(jwks_file))

    class _BlockNetwork:
        @staticmethod
        def get(*args, **kwargs):
            raise AssertionError("静态 JWKS 模式下不应发起网络请求")

    monkeypatch.setattr(auth, "httpx", _BlockNetwork)
    claims = auth.verify_supabase_jwt(_es256_token(sk, _claims()))
    assert claims["sub"] == "user-123"


def test_fetch_jwks_network_timeout_falls_back_to_file_cache(
    jwks_env_no_patch, monkeypatch, tmp_path
):
    """网络握手超时 → 回退本地文件缓存仍可验签（不会把故障放大成 401）。"""
    sk, pub = jwks_env_no_patch
    cache_file = tmp_path / "value_agent_supabase_jwks.json"
    cache_file.write_text(json.dumps({"keys": [pub]}), encoding="utf-8")
    monkeypatch.setenv("SUPABASE_JWKS_CACHE_DIR", str(tmp_path))

    class _TimedOut:
        @staticmethod
        def get(*args, **kwargs):
            raise TimeoutError("_ssl.c:999: The handshake operation timed out")

    monkeypatch.setattr(auth, "httpx", _TimedOut)
    monkeypatch.setattr(auth, "_JWKS_RETRY_DELAY", 0.0)

    claims = auth.verify_supabase_jwt(_es256_token(sk, _claims()))
    assert claims["sub"] == "user-123"


def test_fetch_jwks_network_timeout_no_fallback_raises(jwks_env_no_patch, monkeypatch, tmp_path):
    """网络超时且无任何静态/文件兜底 → 抛原始异常（不静默放行）。"""
    monkeypatch.setenv("SUPABASE_JWKS_CACHE_DIR", str(tmp_path))

    class _TimedOut:
        @staticmethod
        def get(*args, **kwargs):
            raise TimeoutError("_ssl.c:999: The handshake operation timed out")

    monkeypatch.setattr(auth, "httpx", _TimedOut)
    monkeypatch.setattr(auth, "_JWKS_RETRY_DELAY", 0.0)

    with pytest.raises(TimeoutError, match="handshake"):
        auth._fetch_jwks()


def test_fetch_jwks_retries_then_caches_to_file(jwks_env_no_patch, monkeypatch, tmp_path):
    """网络首次失败、重试成功后返回并写入文件缓存。"""
    _, pub = jwks_env_no_patch
    cache_file = tmp_path / "value_agent_supabase_jwks.json"
    monkeypatch.setenv("SUPABASE_JWKS_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(auth, "_JWKS_RETRY_DELAY", 0.0)

    class _Flaky:
        def __init__(self):
            self.calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("handshake timed out")
            return _FakeResp({"keys": [pub]})

    monkeypatch.setattr(auth, "httpx", _Flaky())
    data = auth._fetch_jwks()
    assert data["keys"][0]["kid"] == "test-kid"
    assert cache_file.exists()
    assert json.loads(cache_file.read_text(encoding="utf-8"))["keys"][0]["kid"] == "test-kid"


def test_jwks_url_override(monkeypatch):
    """SUPABASE_JWKS_URL 覆盖默认 Supabase 官方 JWKS 地址（备用境内代理）。"""
    monkeypatch.setenv("SUPABASE_URL", "https://testref.supabase.co")
    monkeypatch.setenv("SUPABASE_JWKS_URL", "https://jwks-proxy.example.com/jwks.json")
    assert auth._jwks_url() == "https://jwks-proxy.example.com/jwks.json"


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data
