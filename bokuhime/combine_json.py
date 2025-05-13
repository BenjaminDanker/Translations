import os
import re
import json
import argparse
import textwrap

# Regex for original Japanese MSG blocks (with \r\n and indentation)
MSG_JP_RX = re.compile(
    r'(?P<prefix>\s*--\s*)?MSG\(\[\[\\r\\n'
    r'(?P<body>.*?)'
    r'\\r\\n\s*(?:(?P=prefix))?\]\]\)',
    re.DOTALL
)
# Regex for translated MSG blocks (no enforced \r\n or indentation)
MSG_EN_RX = re.compile(
    r'MSG\(\[\[(.*?)\]\]\)', re.DOTALL
)

def extract_msg_blocks_jp(text):
    return [m for m in MSG_JP_RX.finditer(text)]

def extract_msg_blocks_en(text):
    return [m for m in MSG_EN_RX.finditer(text)]

def combine_msgs(orig_text, trans_text):
    orig_blocks = extract_msg_blocks_jp(orig_text)
    trans_blocks = extract_msg_blocks_en(trans_text)
    if not orig_blocks:
        orig_blocks = extract_msg_blocks_en(orig_text)
    if not trans_blocks:
        trans_blocks = extract_msg_blocks_en(trans_text)
    if len(orig_blocks) != len(trans_blocks):
        raise ValueError(f"MSG block count mismatch: {len(orig_blocks)} original vs {len(trans_blocks)} translated.")

    new_text = orig_text
    offset = 0
    for orig, trans in zip(orig_blocks, trans_blocks):
        try:
            o_start, o_end = orig.span('body')
            o_content = orig.group('body')
        except IndexError:
            o_start, o_end = orig.span(1)
            o_content = orig.group(1)
        t_content = trans.group(1).strip()

        # Collapse extra newlines.
        t_content = re.sub(r'\r\n+', '\r\n', t_content).strip()
        o_content = re.sub(r'\r\n+', '\r\n', o_content).strip()

        # Get the indentation from the original.
        match = re.match(r'^(\s*)', o_content)
        indent = match.group(1) if match else ''

        # Process English: collapse all whitespace so that it becomes one continuous line.
        english_line = " ".join(t_content.split())
        # Use textwrap to measure how many lines it would occupy at 70 characters.
        en_wrapped = textwrap.wrap(english_line, width=70)
        en_line_count = len(en_wrapped)

        # Process Japanese: split into nonblank lines.
        raw_jp_lines = [line for line in o_content.splitlines() if line.strip()]
        jp_lines = []
        if raw_jp_lines:
            # Check if the first non-blank line (stripped) starts with 【...】
            first_line_stripped_content = raw_jp_lines[0].strip()
            if re.match(r'^【.*?】', first_line_stripped_content):
                # If it does, exclude this line
                jp_lines = raw_jp_lines[1:]
            else:
                jp_lines = raw_jp_lines
        # If raw_jp_lines was empty, jp_lines remains empty.
        
        jp_line_count = len(jp_lines)

        # If the total measured lines exceed 4 and Japanese has more than one line,
        # or if jp_lines is empty, collapse Japanese lines or set to empty.
        if not jp_lines:
            jp_block = ""
        elif (en_line_count + jp_line_count > 4) and (jp_line_count > 1):
            jp_block = indent + " ".join(line.strip() for line in jp_lines)
        else:
            # Lines in jp_lines are from o_content.splitlines() (o_content was stripped),
            # so they already have their correct relative indentation.
            jp_block = "\r\n".join(jp_lines)

        # Do not insert newlines in the English translation output.
        en_block = indent + english_line

        # Adjust English: wrap the first 【...】 with \r\n around it.
        en_block = re.sub(r'^( *)(【.*?】)', r'\1\r\n\2\r\n', en_block, count=1)
        # Adjust Japanese: The removal of 【...】 lines is now handled above by filtering jp_lines.
        # jp_block = re.sub(r'^( *)【.*?】', r'\1', jp_block, count=1) # This line is removed.

        # Combine the two parts with exactly one newline between.
        if en_block and jp_block:
            combined = en_block.rstrip() + '\r\n' + jp_block.lstrip()
        else:
            combined = en_block or jp_block

        new_o_start = o_start + offset
        new_o_end = o_end + offset
        new_text = new_text[:new_o_start] + combined + new_text[new_o_end:]
        offset += len(combined) - (o_end - o_start)
    return new_text

def combine_json(orig_path, trans_path, out_path):
    with open(orig_path, encoding="utf-8") as f:
        orig = json.load(f)
    with open(trans_path, encoding="utf-8") as f:
        trans = json.load(f)
    orig_text = orig["Text"]
    trans_text = trans["Text"]
    combined_text = combine_msgs(orig_text, trans_text)
    out = dict(trans)
    out["Text"] = combined_text
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Combined: {out_path}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--orig", help="Original JSON file or directory")
    parser.add_argument("--trans", help="Translated JSON file or directory")
    parser.add_argument("--out", help="Output file or directory")
    parser.add_argument("--all", action="store_true", help="Process all files in directory")
    args = parser.parse_args()

    if args.all:
        for fn in os.listdir(args.orig):
            if fn.lower().endswith(".json"):
                orig_path = os.path.join(args.orig, fn)
                trans_path = os.path.join(args.trans, fn)
                out_path = os.path.join(args.out, fn)
                if os.path.isfile(orig_path) and os.path.isfile(trans_path):
                    combine_json(orig_path, trans_path, out_path)
    else:
        combine_json(args.orig, args.trans, args.out)

if __name__ == "__main__":
    main()
