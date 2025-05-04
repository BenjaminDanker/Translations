from __future__ import annotations

"""CLI entry‑point for the translation tool‑chain (``/Translations/translate.py``).

Searches for game modules under the project root and hooks them up with the
common helper library in ``/Translations/common``.
"""

import os, sys, importlib, asyncio, logging, time
from pathlib import Path

from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.shortcuts import CompleteStyle
from alive_progress import alive_bar

# ─────────────────────────  GAME REGISTRY  ─────────────────────────
# Each key is the CLI name; value is the fully‑qualified module path
GAMES = {
    "bokuhime": "bokuhime.game",
}

PROJECT_ROOT = Path(__file__).parent  # /Translations
sys.path.insert(0, str(PROJECT_ROOT))  # ensure project root is importable

# ─────────────────────────  CLI HELPERS  ──────────────────────────

def choose_game() -> tuple[str, str]:
    print("Available games:")
    for i, g in enumerate(GAMES, 1):
        print(f"{i}. {g}")
    try:
        idx = int(input("Choose game: ").strip()) - 1
        key = list(GAMES)[idx]
    except (ValueError, IndexError):
        print("Invalid choice"); sys.exit(1)
    return key, GAMES[key]


def complete_json_files(export_dir: os.PathLike):
    files: list[str] = []
    for root, _dirs, fnames in os.walk(export_dir):
        for fn in fnames:
            if fn.lower().endswith(".json"):
                files.append(os.path.relpath(os.path.join(root, fn), export_dir))
    return files


def input_with_completion(text: str, choices: list[str]):
    return prompt(text, completer=WordCompleter(choices, ignore_case=True, match_middle=True), complete_style=CompleteStyle.READLINE_LIKE)

# ─────────────────────────  COMBINE (orig+trans)  ──────────────────

def combine_files(game_mod, fn: str | None = None):
    import subprocess
    orig_dir, trans_dir = game_mod.EXPORT_DIR, game_mod.TRANSL_DIR
    out_dir = getattr(game_mod, "COMBINED_DIR", Path(game_mod.__file__).parent / "Combined")
    os.makedirs(out_dir, exist_ok=True)
    combine_script = Path(game_mod.EXPORT_DIR).parent / "combine_json.py"

    if fn:
        subprocess.run([sys.executable, combine_script, "--orig", f"{orig_dir}/{fn}", "--trans", f"{trans_dir}/{fn}", "--out", f"{out_dir}/{fn}"])
    else:
        subprocess.run([sys.executable, combine_script, "--orig", orig_dir, "--trans", trans_dir, "--out", out_dir, "--all"])

# ────────────────────────────  MAIN  ──────────────────────────────

def main() -> None:
    args = sys.argv[1:]

    game_key: str | None = None
    game_mod_path: str | None = None
    file_arg: str | None = None
    mode: str | None = None
    combine_mode = False

    # —— parse CLI —— 
    if args:
        if args[0] in GAMES:
            game_key, game_mod_path = args[0], GAMES[args[0]]
            if len(args) > 1:
                if args[1] == "all":
                    mode = "all"
                elif args[1] == "combine":
                    combine_mode = True
                    file_arg = None if len(args) < 3 or args[2] == "all" else args[2]
                else:
                    file_arg, mode = args[1], "single"
        else:
            print(f"Unknown game: {args[0]}"); sys.exit(1)

    # —— interactive selection —— 
    if game_key is None:
        game_key, game_mod_path = choose_game()

    game_mod = importlib.import_module(game_mod_path)

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")

    # —— combine only —— 
    if combine_mode:
        combine_files(game_mod, file_arg)
        return

    # Helper for async‑all mode
    async def process_all():
        t0 = time.perf_counter()
        files_to_process = []
        for root, _dirs, files in os.walk(game_mod.EXPORT_DIR):
            for fn in files:
                if not fn.lower().endswith(".json"):
                    continue
                rel = os.path.relpath(os.path.join(root, fn), game_mod.EXPORT_DIR)
                dest = os.path.join(game_mod.TRANSL_DIR, rel)
                if os.path.isfile(dest):
                    continue
                files_to_process.append(rel)

        async def process_with_bar(rel, bar):
            await game_mod.process_file_async(os.path.join(game_mod.EXPORT_DIR, rel))
            bar()

        with alive_bar(len(files_to_process), title="Translating", force_tty=True) as bar:
            await asyncio.gather(*(process_with_bar(rel, bar) for rel in files_to_process))

        logging.info("📦  Finished all files in %.2f s", time.perf_counter() - t0)

    # —— execute chosen mode —— 
    if mode == "single":
        src = os.path.join(game_mod.EXPORT_DIR, file_arg)
        if not os.path.isfile(src):
            logging.error("File not found: %s", src); return
        game_mod.process_file(src, debug=True)
    elif mode == "all":
        asyncio.run(process_all())
    else:
        # —— interactive menu —— 
        print("1. Process a single file")
        print("2. Process all files (async)")
        print("3. Combine original+translated (single file)")
        print("4. Combine all original+translated")
        choice = input("Choose (1 / 2 / 3 / 4): ").strip()
        if choice == "1":
            logging.info("Processing a single file")
            fn = input_with_completion("JSON filename: ", complete_json_files(game_mod.EXPORT_DIR)).strip()
            game_mod.process_file(os.path.join(game_mod.EXPORT_DIR, fn), debug=True)
        elif choice == "2":
            logging.info("Processing all files asynchronously")
            asyncio.run(process_all())
        elif choice == "3":
            logging.info("Combining original+translated (single file)")
            fn = input_with_completion("JSON filename: ", complete_json_files(game_mod.EXPORT_DIR)).strip()
            combine_files(game_mod, fn)
        elif choice == "4":
            logging.info("Combining all original+translated")
            combine_files(game_mod)
        else:
            logging.error("Invalid choice: %s", choice)
            sys.exit(1)


if __name__ == "__main__":
    main()
