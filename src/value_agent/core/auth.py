"""Supabase JWT 验签：FC 后端全局鉴权，只允许前端登录用户调用。

- 当前 token：ECC (P-256) 签名（ES256），公钥从 Supabase JWKS 拉取：
  https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json（内存缓存 1 小时）
- 兼容轮换前老 token：配置 SUPABASE_JWT_SECRET（HS256 共享密钥，可选）后回退验签。
- 依赖：ecdsa（纯 Python P-256 验签，无 cryptography 重依赖）、httpx（项目已用）。
- 网络不可达兜底（FC 大陆出口访问 supabase.co 常 SSL 握手超时）：
  * SUPABASE_JWKS / SUPABASE_JWKS_FILE 静态注入 JWKS 后**完全不发网络请求**（推荐 FC 用）；
  * 未静态注入时：网络拉取带重试，成功后写本地文件缓存（默认 /tmp），失败回退文件缓存；
  * SUPABASE_JWKS_URL 可覆盖 JWKS 地址（备用：自建境内代理/CDN 时指向代理地址）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.parse

import httpx

logger = logging.getLogger(__name__)

_JWKS_TTL_SECONDS = 3600.0
_JWKS_FETCH_TIMEOUT = 8.0
_JWKS_FETCH_ATTEMPTS = 2
_JWKS_RETRY_DELAY = 0.5
_jwks_cache: dict = {"fetched_at": 0.0, "data": None}


def _b64url_decode(seg: str) -> bytes:
    pad = "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg + pad)


def enabled() -> bool:
    """全局鉴权是否启用：配置了 SUPABASE_URL 才强制校验（本地开发无感）。"""
    return bool(os.getenv("SUPABASE_URL"))


def supabase_project_ref() -> str:
    """项目 ref：优先 SUPABASE_URL，回退从 DATABASE_URL（pooler 用户名 postgres.<ref>）推导。"""
    url = os.getenv("SUPABASE_URL", "")
    if url:
        host = urllib.parse.urlparse(url).netloc
        ref = host.split(".")[0]
        if ref:
            return ref
    dsn = os.getenv("DATABASE_URL", "")
    m = re.search(r"//([^:@/]+)@", dsn)
    if m:
        parts = m.group(1).split(".")
        if len(parts) >= 2:
            return parts[1]
    raise ValueError("无法确定 Supabase 项目 ref：请设置 SUPABASE_URL")


def _jwks_url() -> str:
    """JWKS 地址：SUPABASE_JWKS_URL 可覆盖（备用境内代理/CDN），默认 Supabase 官方端点。"""
    override = os.getenv("SUPABASE_JWKS_URL", "").strip()
    if override:
        return override
    return f"https://{supabase_project_ref()}.supabase.co/auth/v1/.well-known/jwks.json"


def _load_static_jwks() -> dict | None:
    """静态 JWKS：优先 SUPABASE_JWKS（JSON 字符串，FC 环境变量），其次 SUPABASE_JWKS_FILE。

    配置后鉴权完全不走网络（FC 大陆出口访问 supabase.co 握手超时的主解）。
    """
    raw = os.getenv("SUPABASE_JWKS", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("keys"):
                logger.info("使用环境变量 SUPABASE_JWKS 注入的 JWKS（跳过网络拉取）")
                return data
            logger.warning("SUPABASE_JWKS 缺少 keys 字段，忽略")
        except Exception as exc:  # noqa: BLE001
            logger.warning("SUPABASE_JWKS 解析失败：%s", exc)
    path = os.getenv("SUPABASE_JWKS_FILE", "").strip()
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("keys"):
                logger.info("使用 SUPABASE_JWKS_FILE %s 的 JWKS（跳过网络拉取）", path)
                return data
            logger.warning("SUPABASE_JWKS_FILE %s 缺少 keys 字段，忽略", path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取 SUPABASE_JWKS_FILE %s 失败：%s", path, exc)
    return None


def _jwks_cache_path() -> str:
    """JWKS 文件缓存路径：显式 SUPABASE_JWKS_FILE 优先，否则 <CACHE_DIR|/tmp> 下。"""
    path = os.getenv("SUPABASE_JWKS_FILE", "").strip()
    if path:
        return path
    base = os.getenv("SUPABASE_JWKS_CACHE_DIR", "").strip() or "/tmp"
    return os.path.join(base, "value_agent_supabase_jwks.json")


def _write_jwks_cache(data: dict) -> None:
    try:
        path = _jwks_cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as exc:  # noqa: BLE001 缓存写失败不影响本次验签
        logger.debug("写入 JWKS 文件缓存失败：%s", exc)


def _read_jwks_cache() -> dict | None:
    path = _jwks_cache_path()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("keys"):
                return data
    except Exception as exc:  # noqa: BLE001
        logger.debug("读取 JWKS 文件缓存失败：%s", exc)
    return None


def _fetch_jwks() -> dict:
    """获取 JWKS：内存缓存 → 静态注入 → 网络拉取（重试+文件缓存）→ 文件缓存回退。"""
    now = time.monotonic()
    if _jwks_cache["data"] is not None and now - _jwks_cache["fetched_at"] < _JWKS_TTL_SECONDS:
        return _jwks_cache["data"]

    # 静态注入：FC 无法出网到 supabase.co 时的主路径，不发起任何网络请求
    static = _load_static_jwks()
    if static is not None:
        _jwks_cache.update(fetched_at=now, data=static)
        return static

    last_exc: Exception | None = None
    for attempt in range(_JWKS_FETCH_ATTEMPTS):
        try:
            resp = httpx.get(_jwks_url(), timeout=_JWKS_FETCH_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict) or not data.get("keys"):
                raise ValueError("JWKS 响应缺少 keys")
            _jwks_cache.update(fetched_at=now, data=data)
            _write_jwks_cache(data)
            return data
        except Exception as exc:  # noqa: BLE001 网络/解析失败走重试或回退
            last_exc = exc
            if attempt < _JWKS_FETCH_ATTEMPTS - 1:
                time.sleep(_JWKS_RETRY_DELAY * (attempt + 1))

    # 网络不可达 → 回退本地文件缓存（过期但通常 key 未轮换，可正常验签）
    cached = _read_jwks_cache()
    if cached is not None:
        logger.warning("拉取 JWKS 失败（%s），回退使用本地文件缓存 %s", last_exc, _jwks_cache_path())
        _jwks_cache.update(fetched_at=now, data=cached)
        return cached
    raise last_exc  # type: ignore[misc]  attempts>=1 时必有异常


def _find_jwks_key(kid: str | None) -> dict | None:
    data = _fetch_jwks()
    for key in data.get("keys", []):
        if kid is None or key.get("kid") == kid:
            return key
    return None


def _verify_es256(signing_input: bytes, signature: bytes, key: dict) -> bool:
    """用 JWKS 里的 EC (P-256) 公钥验 ES256 签名（JWS 原始 r||s 格式）。"""
    import ecdsa

    if key.get("kty") != "EC" or key.get("crv") != "P-256":
        raise ValueError(f"不支持的密钥类型：{key.get('kty')}/{key.get('crv')}")
    try:
        x = int.from_bytes(_b64url_decode(key["x"]), "big")
        y = int.from_bytes(_b64url_decode(key["y"]), "big")
    except KeyError:
        raise ValueError("JWKS 缺少 EC 公钥坐标") from None
    point = ecdsa.ellipticcurve.Point(ecdsa.NIST256p.curve, x, y)
    vk = ecdsa.VerifyingKey.from_public_point(point, curve=ecdsa.NIST256p)
    try:
        return vk.verify(
            signature, signing_input,
            hashfunc=hashlib.sha256, sigdecode=ecdsa.util.sigdecode_string,
        )
    except Exception:  # noqa: BLE001 签名不匹配/格式非法 → 视为校验失败
        return False


def _verify_hs256(signing_input: str, signature: bytes) -> bool:
    """轮换前老 token（HS256）回退验签：SUPABASE_JWT_SECRET 配置了才启用。"""
    secret = os.getenv("SUPABASE_JWT_SECRET", "")
    if not secret:
        return False
    expected = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return hmac.compare_digest(expected, signature)


def _validate_claims(payload: dict) -> None:
    if not isinstance(payload.get("exp"), (int, float)) or payload["exp"] < time.time():
        raise ValueError("token 已过期")
    if payload.get("aud") != "authenticated":
        raise ValueError("仅接受登录用户 token（aud=authenticated）")
    if not payload.get("sub"):
        raise ValueError("token 缺少 sub")
    expected_iss = f"https://{supabase_project_ref()}.supabase.co/auth/v1"
    if payload.get("iss") and payload["iss"] != expected_iss:
        raise ValueError("token 签发方不匹配")


def verify_supabase_jwt(token: str) -> dict:
    """验签并校验 Supabase 用户 JWT，返回 payload；失败抛 ValueError。"""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("JWT 格式错误")
    header_b64, payload_b64, sig_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(sig_b64)
    except Exception as exc:
        raise ValueError("JWT 解码失败") from exc

    alg = header.get("alg", "")
    signing_input = f"{header_b64}.{payload_b64}"
    if alg == "ES256":
        key = _find_jwks_key(header.get("kid"))
        if key is None:
            raise ValueError("JWKS 中找不到匹配的 kid")
        if not _verify_es256(signing_input.encode(), signature, key):
            raise ValueError("签名校验失败")
    elif alg == "HS256":
        if not _verify_hs256(signing_input, signature):
            raise ValueError("签名校验失败")
    else:
        raise ValueError(f"不支持的签名算法：{alg}")

    _validate_claims(payload)
    return payload
