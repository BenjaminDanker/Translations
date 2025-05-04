import os, json, re, asyncio, logging
from typing import List, Tuple

# Import utility helpers from the shared `common` package
from common.io import read_file, write_file  # type: ignore
from common.gpt import translate_blocks_async  # type: ignore

# ─────────────────────────  CONSTANTS  ────────────────────────────
MODEL = "gpt-4.1-mini"
EXPORT_DIR = os.path.join(os.path.dirname(__file__), "Export")
TRANSL_DIR = os.path.join(os.path.dirname(__file__), "Translated")
os.makedirs(TRANSL_DIR, exist_ok=True)

SYSTEM_PROMPT = """
You are the dedicated English translator for the visual-novel “Bokuhime Project.”  
You will receive a JSON object whose values are pieces of Japanese script.  
Return **only** a JSON object with the **same keys** and the translated English text as the values.

────────────────────────────────────────
1.  Canonical glossary  (use these spellings ONLY)

   ── Students
     • 伊草ミナト   (♂ | 1st-year boys div.)     → Minato Ikusa  
     • 伊草エリカ   (♀ persona of Minato)       → Erika Ikusa  
     • 伊草アキラ   (♀ | 1st-year, off-campus) → Akira Ikusa  
     • 鬼灯リラ     (♀ | 2nd-year, Girls div.) → Lira Hoozuki  
     • 龍宮院ウラン (♀ | 2nd-year)             → Uran Ryuguuin  
     • 姫神エルメス (♀ | 3rd-year “Imperial Princess”) → Hermes Himegami  
     • 姫神ダリア   (♀ | 3rd-year “Knight Princess”)   → Daria Himegami  
     • 篠崎ヒユ     (♀ | 1st-year, Erika’s classmate) → Hiyu Shinosaki  
     • 六条オウガ   (♂ | 1st-year boys div.)          → Ouga Rokujou  
     • ♂マスク先輩1/2/3 (♂ | upper-class)            → Mask Senpai #1 / #2 / #3  
     • 伊草マリカ   (♀ | 3rd-year, in coma)          → Marika Ikusa  

   ── Faculty
     • 姫神ネメシア (♀ | Director)            → Nemesia Himegami  

   ── Key terms
     • 私立百合愛学園      → Yuriai Private Academy  
     • 四姫                  → Four Princesses  
     • 姫選挙                → Princess Election  
     • 戦姫                  → Battle Princess  

If an unlisted proper noun appears, keep it in romaji.

────────────────────────────────────────
2.  Pronoun & gender rules  
   • Characters marked (♂) = he/him.  (♀) = she/her.  
   • Minato: he/him when identity is known; Erika: she/her in public.  
   • Narration (Minato’s POV) = neutral male first-person.

────────────────────────────────────────
3.  Speech-style cheatsheet  
   • Erika  = polite / earnest  
   • Lira   = flashy gal-slang, calls others “weeds”  
   • Uran   = serene, classical diction  
   • Hermes = playful yet regal  
   • Daria  = chivalrous big-sister tone  
   • Hiyu   = hyper, nose-bleed gags, calls Erika “Sister”  
   • Ouga   = boastful “gym-bro”  
   • Akira  = sharp, teasing hikikomori

────────────────────────────────────────
4.  Tag & newline guidelines  (strict)  
   1. Translate natural Japanese into natural, fluent English—no additions, deletions, or re-ordering.  
   2. Preserve every markup tag exactly as-is: `<sprite …>`, `<L>`, `<R>`, `<r=…>`, `</r>`, etc. Do **not** translate attributes.  
   3. For ruby tags (`<r=腰>枯死</r>`), translate **only** the inner text (`枯死` → `wither`) and leave tags untouched.  
   4. Speaker headers look like `\r\n【ミナト】笑顔\r\n`.  Translate **only** the name inside `【】` (→ `【Minato】笑顔`).  Keep pose/emotion labels (e.g. `笑顔`) in Japanese.  
   5. Keep the `\r\n` that immediately surrounds each speaker header; remove **all other** `\r\n`.  
   6. Collapse multiple spaces created by newline removal into one.  
   7. Do not add or remove other whitespace or punctuation unless required by English grammar.

────────────────────────────────────────
5.  Output contract  
   • Input arrives as JSON: `{"0":"…","1":"…",…}`.  
   • Reply with JSON having the **same keys**, values translated.  
   • No extra quotes, no commentary, no framing text—**only** the JSON object.

"""


# ───────────────────────  TAG PROTECTION  ─────────────────────────
_tag_re = re.compile(r"<[^>]+>")

def _protect(text: str):
    """Replace markup tags with placeholders so GPT won't touch them."""
    tag_map: dict[str, str] = {}
    def repl(m: re.Match[str]) -> str:
        tag = m.group(0)
        key = f"<TAG{len(tag_map)}>"
        tag_map[key] = tag
        return key
    safe = _tag_re.sub(repl, text)
    return safe, tag_map

def _restore(text: str, tag_map: dict):
    """Restore placeholders back to original markup tags."""
    for k, v in tag_map.items():
        text = text.replace(k, v)
    return text

# ───────────────────  NEWLINE CLEAN‑UP  ──────────────────────────
_speaker_re = re.compile(r"(\r\n)(\s*【[^】]+】[^\r\n]*)(\r\n)")

def _cleanup_newlines(s: str) -> str:
    logging.debug("Original input: %r", s)

    placeholders: dict[str,str] = {}

    def protect(m: re.Match[str]) -> str:
        key = f"__SPK{len(placeholders)}__"
        # stash INCLUDING both leading and trailing CRLFs
        placeholders[key] = f"{m.group(1)}{m.group(2)}{m.group(3)}"
        return key

    # 1) pull out full CRLF+header+CRLF
    tmp = _speaker_re.sub(protect, s)
    logging.debug("After speaker header extraction: %r", tmp)
    logging.debug("Placeholders: %r", placeholders)

    # 2) remove all other CRLFs
    tmp = tmp.replace("\r\n", " ")
    logging.debug("After CRLF removal: %r", tmp)

    # 3) collapse spaces
    tmp = re.sub(r"\s+", " ", tmp)
    logging.debug("After space collapsing: %r", tmp)

    # 4) restore the headers with their CRLF wrappers
    for key, val in placeholders.items():
        tmp = tmp.replace(key, val)
    logging.debug("After restoring headers: %r", tmp)

    result = tmp
    logging.debug("Final result: %r", result)
    return result

# ─────────────────────  MSG BLOCK HANDLING  ──────────────────────
_msg_re = re.compile(r"MSG\(\[\[([\s\S]*?)\]\]\)")

def _extract_blocks(lua_text: str):
    """Return message blocks and their spans inside the Lua script."""
    blocks: List[str] = []
    spans: List[Tuple[int, int]] = []
    for m in _msg_re.finditer(lua_text):
        blocks.append(m.group(1))
        spans.append((m.start(1), m.end(1)))
    return blocks, spans

# ─────────────────────  FILE PROCESSORS  ─────────────────────────
async def process_file_async(path: str, dest_path: str | None = None, *, debug: bool = False):
    """Translate all MSG() blocks in a single exported JSON file asynchronously."""
    if dest_path is None:
        rel = os.path.relpath(path, EXPORT_DIR)
        dest_path = os.path.join(TRANSL_DIR, rel)

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    logging.debug("Processing %s → %s", path, dest_path)

    raw_json = json.loads(read_file(path))
    lua_src: str = raw_json["Text"]

    # ── extract message blocks ────────────────────────────────
    blocks, spans = _extract_blocks(lua_src)
    if not blocks:  # nothing to translate
        write_file(dest_path, json.dumps(raw_json, ensure_ascii=False, indent=2))
        return

    # ── translate ─────────────────────────────────────────────
    translated_blocks, success = await translate_blocks_async(
        blocks,
        system_prompt=SYSTEM_PROMPT,
        model=MODEL,
        protect=_protect,
        restore=_restore,
    )
    if not success:
        logging.warning("⚠️  Some blocks failed to translate in %s", path)
        return

    cleaned_blocks = [_cleanup_newlines(t) for t in translated_blocks]

    # ── re‑insert translations into original Lua text ─────────
    buf: list[str] = []
    last = 0
    for (start, end), new in zip(spans, cleaned_blocks):
        buf.append(lua_src[last:start])
        buf.append(new)
        last = end
    buf.append(lua_src[last:])

    raw_json["Text"] = "".join(buf)

    # ── write out ─────────────────────────────────────────────
    write_file(dest_path, json.dumps(raw_json, ensure_ascii=False, indent=2))
    logging.debug("✅  Wrote %s", dest_path)


def process_file(path: str, dest_path: str | None = None, *, debug: bool = False):
    """Synchronous wrapper for tooling that expects a blocking call."""
    asyncio.run(process_file_async(path, dest_path, debug=debug))

# ─────────────────────  CLI TEST HOOK  ───────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python -m bokuhime.game <json-file> [output-file]")
        sys.exit(1)
    in_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None
    process_file(in_path, out_path, debug=True)
