#!/bin/bash

FIRSTDIR=$(pwd)

# Store the original directory
ORIGINAL_DIR="/Users/tresmith/Documents/fish-speech"

# Path to the fish-speech directory and virtual environment
FISH_SPEECH_DIR="$ORIGINAL_DIR/fish-speech"
VENV_PATH="$ORIGINAL_DIR/venv"

# # First run the writer script with the provided argument
# python3 "writer.py" "$1"

# Change to the fish-speech directory
cd "$FISH_SPEECH_DIR"

# Activate the virtual environment
source "$VENV_PATH/bin/activate"

# # Run the wrapper script with any arguments passed to this script
# python3 "$FISH_SPEECH_DIR/local_tts.py" "$@"
python3 "$FISH_SPEECH_DIR/book_tts.py"

# Deactivate the virtual environment
deactivate

# Change back to the original directory
# cd "$FIRSTDIR"

# python3 "make_vid.py" "$@"