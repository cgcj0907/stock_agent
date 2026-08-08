"""清除历史会话中持久化的 LLM api_key（密钥不落库）。

背景：早期版本把完整 llm_config（含明文 api_key）写进会话 payload；
现在 Session.to_dict 已剔除 api_key，本脚本用于回填清理历史数据。

用法：
  SESSION_STORE=supabase python -m scripts.scrub_session_secrets   # 生产 Supabase（原子 SQL）
  SESSION_STORE=sqlite  SESSIONS_DB=data/sessions.db python -m scripts.scrub_session_secrets
"""
from __future__ import annotations

from value_agent.core.config import _load_dotenv
from value_agent.sessions import create_session_store


def _scrub_supabase(store) -> int:
    """Supabase：单条原子 UPDATE 移除所有 payload 中的 api_key（避免逐条 round-trip 卡死）。"""
    with store._conn.cursor() as cur:
        cur.execute("select count(*) from sessions where payload->'llm_config' ? 'api_key'")
        before = cur.fetchone()[0]
        cur.execute(
            """
            update sessions
            set payload = jsonb_set(payload, '{llm_config}', (payload->'llm_config') - 'api_key')
            where payload->'llm_config' ? 'api_key'
            """
        )
    return before


def main() -> int:
    _load_dotenv()  # 读取 SESSION_STORE / DATABASE_URL（默认本地 sqlite，勿误清错库）
    store = create_session_store()
    try:
        if getattr(store, "name", "") == "supabase":
            scrubbed = _scrub_supabase(store)
        else:
            scrubbed = 0
            for session in store.list():
                cfg = session.llm_config or {}
                if not cfg.get("api_key"):
                    continue
                cfg.pop("api_key", None)
                session.llm_config = cfg or None
                store.save(session)
                scrubbed += 1
                print(f"[scrub] {session.id} ({session.company_code}) 已移除 api_key")
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()
    print(f"[scrub] 完成，共清理 {scrubbed} 个会话")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
