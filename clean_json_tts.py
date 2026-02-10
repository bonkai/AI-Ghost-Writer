import json
import re
import os

def clean_text_for_tts(text):
    """
    Cleans a string for Text-to-Speech (TTS) processing.
    - Replaces newlines with spaces.
    - Replaces hyphens with spaces.
    - Removes characters other than letters, numbers, spaces, and
      standard punctuation useful for TTS (.,?!'"—…).
    - Consolidates multiple spaces into single spaces.
    - Trims leading/trailing whitespace.
    """
    if not isinstance(text, str):
        # Handle cases where a value might not be text (e.g., null, number)
        print(f"Warning: Encountered non-string value: {text}. Skipping cleaning.")
        return text # Or return an empty string: return ""

    # 1. Replace newlines with spaces
    text = text.replace('\n', ' ')

    # 2. Replace hyphens with spaces (often better for TTS than just removing)
    text = text.replace('-', ' ')

    # 3. Define allowed characters: letters, numbers, space, and common punctuation
    # Includes: . , ? ! ' " — … (period, comma, q-mark, e-mark, single/double quotes, em-dash, ellipsis)
    # You can adjust this set if your TTS handles other characters well or poorly.
    # The regex pattern matches anything NOT in the allowed set.
    allowed_chars_pattern = r"[^a-zA-Z0-9 .,?!'\"—… ]"
    text = re.sub(allowed_chars_pattern, '', text)

    # 4. Consolidate multiple whitespace characters into a single space
    text = re.sub(r'\s+', ' ', text)

    # 5. Trim leading/trailing whitespace
    text = text.strip()

    return text

def process_json_file(input_filepath, output_filepath):
    """
    Reads a JSON file, cleans the string values using clean_text_for_tts,
    and writes the result to a new JSON file.
    """
    try:
        with open(input_filepath, 'r', encoding='utf-8') as infile:
            data = json.load(infile)
    except FileNotFoundError:
        print(f"Error: Input file not found at '{input_filepath}'")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{input_filepath}'. Check file format.")
        return
    except Exception as e:
        print(f"An unexpected error occurred while reading the file: {e}")
        return

    cleaned_data = {}
    print(f"Processing file: {input_filepath}...")

    for key, value in data.items():
        print(f"  Cleaning item '{key}'...")
        cleaned_data[key] = clean_text_for_tts(value)
        # Optional: Print original vs cleaned for verification
        # if isinstance(value, str):
        #    print(f"    Original: {value[:100]}...") # Print first 100 chars
        #    print(f"    Cleaned:  {cleaned_data[key][:100]}...")

    try:
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_filepath)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"Created output directory: {output_dir}")

        with open(output_filepath, 'w', encoding='utf-8') as outfile:
            # Use indent for readability of the output JSON file
            # Use ensure_ascii=False to keep characters like em-dash (—) and ellipsis (…) intact
            json.dump(cleaned_data, outfile, indent=4, ensure_ascii=False)
        print(f"\nSuccessfully cleaned data and saved to '{output_filepath}'")

    except Exception as e:
        print(f"An error occurred while writing the output file: {e}")

# --- Configuration ---
INPUT_JSON_FILE = 'story_output.json'  # <--- Change this to your input file name
OUTPUT_JSON_FILE = 'cleaned_story_pieces_tts.json' # <--- Change this for the output file name
# -------------------

if __name__ == "__main__":
    # Basic check if input file exists before starting
    if not os.path.exists(INPUT_JSON_FILE):
         print(f"Error: The specified input file '{INPUT_JSON_FILE}' does not seem to exist.")
         print("Please make sure the file name and path are correct.")
    else:
        process_json_file(INPUT_JSON_FILE, OUTPUT_JSON_FILE)
