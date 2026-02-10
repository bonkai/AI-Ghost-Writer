import re
import json
import html
import enchant  # For dictionary-based word checking

def read_text_and_split_into_sections(text_path, json_output_path="output.json"):
    """
    Reads a text file, cleans it, splits it into sections,
    and saves the sections to a JSON file (handling Unicode escapes).

    Args:
        text_path: The path to the text file.
        json_output_path: The path to the output JSON file (default: "output.json").
    """
    try:
        with open(text_path, 'r', encoding='utf-8') as file:
            all_text = file.read()
            all_text = refine_newlines(all_text)

        sections = split_into_sections(all_text)

        # Export to JSON, handling Unicode escapes
        save_sections_to_json(sections, json_output_path)

    except FileNotFoundError:
        print(f"Error: File not found at '{text_path}'")
    except Exception as e:
        print(f"An error occurred: {e}")

def refine_newlines(text):
    """
    Improves newline handling and hyphenated word joining.

    Args:
        text: The raw extracted text.

    Returns:
        The text with more accurately placed newlines and joined hyphenated words.
    """

    if text is None:
        return ""

    # 1. Replace multiple newlines with a single newline
    text = re.sub(r"\n{2,}", "\n", text)

    # 2. Join lines not ending with punctuation, handling common abbreviations
    lines = text.splitlines()
    processed_lines = []
    for i, line in enumerate(lines):
        if line.endswith((".", "?", "!", "Mr.", "Dr.", "Ms.")):
            processed_lines.append(line)
        elif i + 1 < len(lines):
            if lines[i+1] and lines[i+1][0].islower():
                processed_lines.append(line + " ")
            else:
                processed_lines.append(line)
        else:
            processed_lines.append(line)
    text = "".join(processed_lines)

    # 3. Improved hyphenated word joining
    def join_hyphenated_word(match):
        word_start = match.group(1)
        word_end = match.group(2)

        # Dictionary check (using enchant)
        d = enchant.Dict("en_US")  # Or your preferred language
        if d.check(word_start) and d.check(word_end):
            return match.group(0)  # Don't join if both parts are valid words

        return word_start + word_end

    text = re.sub(r"(\w+)-\s*[\n\r]+\s*(\w+)", join_hyphenated_word, text)

    return text.strip() if text else ""

def split_into_sections(text):
    """
    Splits the text into sections based on word count and sentence boundaries.

    Args:
        text: The cleaned text from the file.

    Returns:
        A list of strings, where each string is a section.
    """
    sentences = re.split(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s", text)  # Improved sentence splitting
    sections = []
    current_section = []
    word_count = 0

    for sentence in sentences:
        sentence_word_count = len(sentence.split())
        if word_count + sentence_word_count >= 40:
            current_section.append(sentence)
            sections.append(" ".join(current_section))
            current_section = []
            word_count = 0
        else:
            current_section.append(sentence)
            word_count += sentence_word_count

    # Add any remaining sentences to the last section
    if current_section:
        sections.append(" ".join(current_section))

    return sections

def save_sections_to_json(sections, json_output_path):
    """
    Saves the sections to a JSON file, handling Unicode escapes.

    Args:
        sections: A list of strings representing the sections.
        json_output_path: The path to the output JSON file.
    """
    data = {str(i + 1): section for i, section in enumerate(sections)}

    with open(json_output_path, "w", encoding="utf-8") as f:  # Specify UTF-8 encoding
        json_string = json.dumps(data, indent=4, ensure_ascii=False)  # Disable ASCII escaping
        decoded_json_string = html.unescape(json_string)  # Decode HTML entities
        f.write(decoded_json_string)

# Example usage:
text_file_path = "story.txt"  # Replace with your text file path
json_file_path = "story_output.json"  # Replace with desired output path
read_text_and_split_into_sections(text_file_path, json_file_path)