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
