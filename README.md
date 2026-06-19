# AI Ghost Writer

A long-form fiction pipeline that writes a story **scene by scene, draft by draft** — not
one giant generation. Each scene is drafted multiple times, a best/refined version is
selected, and the final text is cleaned and prepared for text-to-speech narration.

## Pipeline

1. **Draft** — generate a story scene-by-scene, producing several drafts per scene
   (`scene_N_draft_1..5`).
2. **Select / refine** — converge each scene to a final version.
3. **TTS prep** — `clean_json_tts.py` normalizes the prose for narration (strips
   problem characters, collapses whitespace, fixes punctuation) and emits clean,
   TTS-ready text pieces.

## Stack

- Python, a local LLM for drafting, JSON intermediates for the TTS hand-off
- Configurable via `config.ini`

## Layout

- `clean_json_tts.py` — the TTS text-cleaning stage
- `<story>/story_output/` — per-scene drafts and final text (example: `dragonprincess/`)

## Run

```bash
python clean_json_tts.py     # clean a generated story's pieces for narration
```
