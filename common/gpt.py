from __future__ import annotations
import functools

"""Thin OpenAI helper wrapping chat‑completions with JSON I/O + rate‑limits.

This version has been simplified to work with the updated ``game.py``:
* ``protect`` must now return **two** values: (safe_text, meta).
* ``restore`` must accept exactly those two values in the same order.
* Sprite‑map handling has been removed (not needed).
"""

from typing import Any, Dict, List, Tuple
import os, json, random, string, logging, time, asyncio

import openai  # type: ignore
from dotenv import load_dotenv  # type: ignore

load_dotenv()
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ───────────────────────────  UTILS  ─────────────────────────────

def _randid(k: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))


def _parse_reset(val: str | None) -> float:
    """Parse OpenAI reset header value (e.g. ``"327ms"``, ``"2.866s"``) → seconds."""
    if not val:
        return 0
    val = val.strip().lower()
    if val.endswith("ms"):
        return float(val[:-2]) / 1000
    if val.endswith("s"):
        return float(val[:-1])
    try:
        return float(val)
    except Exception:
        return 0.0


# ──────────────────────  CORE WRAPPERS  ──────────────────────────

def _chat_json(system_prompt: str, payload: Dict[str, str], *, model: str):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    return client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=messages,
    )


# ─────────────────────  BLOCK TRANSLATION  ───────────────────────

TranslateResult = Tuple[List[str], bool]  # (translated_blocks, all_success)


def translate_blocks(
    blocks: List[str],
    *,
    system_prompt: str,
    model: str,
    protect,
    restore,
    max_retries: int = 3,
    min_remaining_requests: int = 5,
    min_remaining_tokens: int = 5000,
) -> TranslateResult:
    """Translate each *block* via GPT while enforcing rate‑limits.

    ``protect``  – callable ``jp_str → (safe_text, meta)``
    ``restore``  – callable ``(translated_safe, meta) → restored_text``
    """

    # map `str(i)` → safe_text so we can send many blocks at once
    safe_dict: Dict[str, str] = {}
    metas: List[Any] = []

    for i, jp in enumerate(blocks):
        safe, meta = protect(jp)
        safe_dict[str(i)] = safe
        metas.append(meta)

    remaining = dict(safe_dict)  # copy
    completed: Dict[str, str] = {}

    # Track rate‑limit headers
    reqs_left = tokens_left = float("inf")
    reqs_reset = tokens_reset = 0.0
    attempt = 0
    success = True

    while remaining and attempt < max_retries:
        attempt += 1

        now = time.time()
        if reqs_left <= min_remaining_requests and reqs_reset > now:
            time.sleep(reqs_reset - now)
        if tokens_left <= min_remaining_tokens and tokens_reset > now:
            time.sleep(tokens_reset - now)

        try:
            resp = _chat_json(system_prompt, remaining, model=model)
        except openai.RateLimitError as e:  # type: ignore[attr-defined]
            hdrs = getattr(e, "response", None)
            if hdrs is not None and hasattr(hdrs, "headers"):
                rl = hdrs.headers
                time.sleep(_parse_reset(rl.get("x-ratelimit-reset-requests")))
            continue
        except Exception as exc:
            logging.exception("GPT call failed: %s", exc)
            success = False
            break

        # —— header bookkeeping ——
        hdrs = getattr(resp, "response", None)
        if hdrs is not None:
            hdrs = resp.response.headers  # type: ignore[assignment]
            try:
                reqs_left = int(hdrs.get("x-ratelimit-remaining-requests", reqs_left))
                tokens_left = int(hdrs.get("x-ratelimit-remaining-tokens", tokens_left))
                now = time.time()
                reqs_reset = now + _parse_reset(hdrs.get("x-ratelimit-reset-requests"))
                tokens_reset = now + _parse_reset(hdrs.get("x-ratelimit-reset-tokens"))
            except Exception:
                pass

        # —— merge GPT output ——
        try:
            out = json.loads(resp.choices[0].message.content)  # type: ignore[index]
        except json.JSONDecodeError:
            logging.warning("Bad JSON from GPT, retrying…")
            continue

        for k, v in out.items():
            if k in remaining:
                completed[k] = v
                remaining.pop(k)

    if remaining:
        # didn’t manage to translate everything
        success = False
        completed.update({k: v for k, v in remaining.items()})  # use safe text

    # —— restore original formatting ——
    results: List[str] = []
    for i in range(len(blocks)):
        raw_safe = completed[str(i)]
        results.append(restore(raw_safe, metas[i]))

    return results, success


async def translate_blocks_async(*args, **kwargs) -> TranslateResult:  # type: ignore[override]
    loop = asyncio.get_event_loop()
    func = functools.partial(translate_blocks, *args, **kwargs)
    return await loop.run_in_executor(None, func)