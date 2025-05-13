import os
import re
import json
import argparse

# Regex for MSG blocks
MSG_RX = re.compile(r'MSG\(\[\[(.*?)\]\]\)', re.DOTALL)
# Regex for speaker note: captures (【Speaker】), (Note), and trailing (\r\n)
# Works for examples like 【Erika】Serious\r\n
SPEAKER_NOTE_RX = re.compile(r'(【[^】]+】)\s*([^\r\n]+)(\r\n)')

def remove_notes_from_block_content(block_content):
    """
    Removes author notes from speaker tags within a single MSG block's content.
    Example: "【Erika】Serious\r\n" becomes "【Erika】\r\n"
    """
    return SPEAKER_NOTE_RX.sub(r'\1\3', block_content)

def process_text_field(text_content):
    """
    Processes the entire "Text" field, finding all MSG blocks and cleaning them.
    """
    new_text_content = text_content
    offset = 0
    for match in MSG_RX.finditer(text_content):
        original_block_content = match.group(1)
        modified_block_content = remove_notes_from_block_content(original_block_content)

        if modified_block_content != original_block_content:
            # Replace the content of the current MSG block
            # match.span(1) gives the start and end of the content *within* MSG([[]])
            start, end = match.span(1)
            
            current_pos_start = start + offset
            current_pos_end = end + offset

            new_text_content = (
                new_text_content[:current_pos_start] +
                modified_block_content +
                new_text_content[current_pos_end:]
            )
            offset += len(modified_block_content) - len(original_block_content)
    return new_text_content

def process_json_file(input_path, output_path):
    """
    Reads a JSON file, processes its "Text" field, and writes the modified JSON to output_path.
    """
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {input_path}: {e}")
        return

    if 'Text' in data and isinstance(data['Text'], str):
        data['Text'] = process_text_field(data['Text'])
    else:
        print(f"Warning: 'Text' field not found or not a string in {input_path}. Skipping note removal for this file.")

    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Processed: {input_path} -> {output_path}")
    except Exception as e:
        print(f"Error writing {output_path}: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="Remove author notes after in-game speaker tags within MSG blocks in JSON files."
    )
    parser.add_argument("--input", required=True, help="Input JSON file or directory.")
    parser.add_argument("--output", required=True, help="Output JSON file or directory.")
    
    args = parser.parse_args()

    if os.path.isdir(args.input):
        if not os.path.exists(args.output):
            os.makedirs(args.output)
        elif not os.path.isdir(args.output):
            print("Error: If input is a directory, output must also be a directory.")
            parser.print_help()
            return

        for filename in os.listdir(args.input):
            if filename.lower().endswith(".json"):
                input_file_path = os.path.join(args.input, filename)
                output_file_path = os.path.join(args.output, filename)
                if os.path.isfile(input_file_path):
                    process_json_file(input_file_path, output_file_path)
    elif os.path.isfile(args.input):
        output_file_path = args.output
        if os.path.isdir(args.output):
            # If output is a directory, save with the same filename inside that directory
            output_file_path = os.path.join(args.output, os.path.basename(args.input))
            os.makedirs(args.output, exist_ok=True)
        else:
            # Ensure the parent directory for the output file exists
            output_dir = os.path.dirname(output_file_path)
            if output_dir: # Create parent directory if it's specified and doesn't exist
                os.makedirs(output_dir, exist_ok=True)
        
        process_json_file(args.input, output_file_path)
    else:
        print(f"Error: Input path '{args.input}' is not a valid file or directory.")
        parser.print_help()

if __name__ == "__main__":
    main()