# Install required libraries: pip install striprtf configparser tqdm
import requests
import json
import os
import argparse
import logging
import time
import datetime
import sys
import configparser # Import configparser
import shutil # For archiving failed scenes
from striprtf.striprtf import rtf_to_text
from tqdm import tqdm # Import tqdm

# --- Load Configuration ---
# Moved config loading to the top for early access to constants
config = configparser.ConfigParser(interpolation=None) # Disable interpolation for simple key-value
config_file_path = 'config.ini'
# --- Default values (used if config file is missing keys or file itself) ---
# Define defaults clearly
DEFAULT_OLLAMA_API_URL = 'http://localhost:11434/api/chat'
DEFAULT_OLLAMA_MODEL = 'gemma3:27b'
DEFAULT_API_TIMEOUT = 480
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5
DEFAULT_ROLES_FILE = 'llm_roles.json'
DEFAULT_BASE_OUTPUT_DIR = 'story_rewrites'
DEFAULT_LOG_FILENAME = 'rewrite_generator.log'
DEFAULT_PLAN_FILENAME = 'loaded_scene_plan.json'
DEFAULT_FINAL_STORY_FILENAME = 'rewritten_story.txt'
DEFAULT_RESUME_STATE_FILENAME = 'resume_state.json'
DEFAULT_ORIGINAL_DRAFT_PLAINTEXT_FILENAME = 'original_draft_plain.txt'
DEFAULT_MAX_REVISIONS_PER_SCENE = 4
DEFAULT_CONTEXT_SIZE_WARNING_THRESHOLD = 480000 # Adjusted default based on previous discussion
DEFAULT_NUM_FULL_TEXT_CONTEXT_SCENES = 7 # Adjusted default

# Initialize variables with defaults
OLLAMA_API_URL = DEFAULT_OLLAMA_API_URL; DEFAULT_MODEL_CONFIG = DEFAULT_OLLAMA_MODEL; API_TIMEOUT = DEFAULT_API_TIMEOUT; MAX_RETRIES = DEFAULT_MAX_RETRIES; RETRY_DELAY = DEFAULT_RETRY_DELAY; ROLES_FILE = DEFAULT_ROLES_FILE; BASE_OUTPUT_DIR = DEFAULT_BASE_OUTPUT_DIR; LOG_FILENAME = DEFAULT_LOG_FILENAME; PLAN_FILENAME = DEFAULT_PLAN_FILENAME; FINAL_STORY_FILENAME = DEFAULT_FINAL_STORY_FILENAME; RESUME_STATE_FILENAME = DEFAULT_RESUME_STATE_FILENAME; ORIGINAL_DRAFT_PLAINTEXT_FILENAME = DEFAULT_ORIGINAL_DRAFT_PLAINTEXT_FILENAME; MAX_REVISIONS_PER_SCENE = DEFAULT_MAX_REVISIONS_PER_SCENE; CONTEXT_SIZE_WARNING_THRESHOLD = DEFAULT_CONTEXT_SIZE_WARNING_THRESHOLD; NUM_FULL_TEXT_CONTEXT_SCENES = DEFAULT_NUM_FULL_TEXT_CONTEXT_SCENES

if not os.path.exists(config_file_path):
    # Use print here as logging isn't set up yet
    print(f"WARNING: Configuration file '{config_file_path}' not found. Using default values.")
else:
    try:
        config.read(config_file_path)
        # Read values, falling back to defaults if key is missing or section is missing
        OLLAMA_API_URL = config.get('Ollama', 'ApiUrl', fallback=DEFAULT_OLLAMA_API_URL)
        DEFAULT_MODEL_CONFIG = config.get('Ollama', 'DefaultModel', fallback=DEFAULT_OLLAMA_MODEL)
        API_TIMEOUT = config.getint('Ollama', 'ApiTimeout', fallback=DEFAULT_API_TIMEOUT)
        MAX_RETRIES = config.getint('Ollama', 'MaxRetries', fallback=DEFAULT_MAX_RETRIES)
        RETRY_DELAY = config.getint('Ollama', 'RetryDelay', fallback=DEFAULT_RETRY_DELAY)
        ROLES_FILE = config.get('Files', 'RolesFile', fallback=DEFAULT_ROLES_FILE)
        BASE_OUTPUT_DIR = config.get('Files', 'BaseOutputDir', fallback=DEFAULT_BASE_OUTPUT_DIR)
        LOG_FILENAME = config.get('Files', 'LogFilename', fallback=DEFAULT_LOG_FILENAME)
        PLAN_FILENAME = config.get('Files', 'PlanFilename', fallback=DEFAULT_PLAN_FILENAME)
        FINAL_STORY_FILENAME = config.get('Files', 'FinalStoryFilename', fallback=DEFAULT_FINAL_STORY_FILENAME)
        RESUME_STATE_FILENAME = config.get('Files', 'ResumeStateFilename', fallback=DEFAULT_RESUME_STATE_FILENAME)
        ORIGINAL_DRAFT_PLAINTEXT_FILENAME = config.get('Files', 'OriginalDraftPlaintextFilename', fallback=DEFAULT_ORIGINAL_DRAFT_PLAINTEXT_FILENAME)
        MAX_REVISIONS_PER_SCENE = config.getint('Workflow', 'MaxRevisionsPerScene', fallback=DEFAULT_MAX_REVISIONS_PER_SCENE)
        CONTEXT_SIZE_WARNING_THRESHOLD = config.getint('Workflow', 'ContextSizeWarningThreshold', fallback=DEFAULT_CONTEXT_SIZE_WARNING_THRESHOLD)
        NUM_FULL_TEXT_CONTEXT_SCENES = config.getint('Workflow', 'NumFullTextContextScenes', fallback=DEFAULT_NUM_FULL_TEXT_CONTEXT_SCENES)
    except configparser.Error as e:
        print(f"Error reading configuration file '{config_file_path}': {e}. Using defaults.")
        # Ensure all variables are reset to default if there was any config error
        OLLAMA_API_URL = DEFAULT_OLLAMA_API_URL; DEFAULT_MODEL_CONFIG = DEFAULT_OLLAMA_MODEL; API_TIMEOUT = DEFAULT_API_TIMEOUT; MAX_RETRIES = DEFAULT_MAX_RETRIES; RETRY_DELAY = DEFAULT_RETRY_DELAY; ROLES_FILE = DEFAULT_ROLES_FILE; BASE_OUTPUT_DIR = DEFAULT_BASE_OUTPUT_DIR; LOG_FILENAME = DEFAULT_LOG_FILENAME; PLAN_FILENAME = DEFAULT_PLAN_FILENAME; FINAL_STORY_FILENAME = DEFAULT_FINAL_STORY_FILENAME; RESUME_STATE_FILENAME = DEFAULT_RESUME_STATE_FILENAME; ORIGINAL_DRAFT_PLAINTEXT_FILENAME = DEFAULT_ORIGINAL_DRAFT_PLAINTEXT_FILENAME; MAX_REVISIONS_PER_SCENE = DEFAULT_MAX_REVISIONS_PER_SCENE; CONTEXT_SIZE_WARNING_THRESHOLD = DEFAULT_CONTEXT_SIZE_WARNING_THRESHOLD; NUM_FULL_TEXT_CONTEXT_SCENES = DEFAULT_NUM_FULL_TEXT_CONTEXT_SCENES
    except ValueError as e:
        print(f"Error converting configuration value in '{config_file_path}': {e}. Check integer values (ApiTimeout, MaxRetries, RetryDelay, MaxRevisionsPerScene, ContextSizeWarningThreshold, NumFullTextContextScenes). Exiting.")
        sys.exit(1)


# --- Hardcoded Story Summary ---
STORY_SUMMARY = """
# (Your high-level story summary)
A brief summary describing the core concept, protagonist, and main conflict
of the story being rewritten.
"""

# --- Global variable ---
unique_run_dir = None

# --- RTF Loading Function ---
def load_rtf_as_text(filepath):
    """Loads an RTF file and converts it to plain text."""
    logging.info(f"Attempting to load RTF draft from: {filepath}")
    if not os.path.exists(filepath): logging.error(f"RTF draft file not found: {filepath}"); return None
    try:
        # Specify encoding explicitly, handle potential errors gracefully
        with open(filepath, 'r', encoding='ascii', errors='ignore') as f: # Try ASCII first as RTF often uses it
            rtf_content = f.read()
        plain_text = rtf_to_text(rtf_content)
        if not plain_text: logging.error(f"RTF conversion resulted in empty text for {filepath}. Check file content or striprtf compatibility."); return None
        word_count = len(plain_text.split())
        logging.info(f"Successfully loaded and converted RTF file. Approx word count: {word_count}")
        if word_count < 50: logging.warning(f"RTF conversion resulted in very short text ({word_count} words).")
        return plain_text
    except FileNotFoundError: logging.error(f"RTF file not found during open: {filepath}"); return None
    except Exception as e: logging.error(f"Error loading or converting RTF file {filepath}: {e}"); return None

# --- Role Loading ---
def load_roles(filepath=ROLES_FILE):
    """Loads the LLM role prompts from the roles file."""
    if not os.path.exists(filepath): logging.error(f"Role file not found: {filepath}"); raise FileNotFoundError(f"Role file not found: {filepath}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f: roles = json.load(f)
        # Ensure all roles used by the script are present
        required_roles = ["PrimaryWriter", "CriticalEditor", "FocusedRewriter", "ConsistencyChecker", "DialogueDoctor", "PacingTensionAnalyst", "SceneSummarizer"]
        missing_roles = [r for r in required_roles if r not in roles]
        if missing_roles: logging.error(f"FATAL: Missing required roles in {filepath}: {missing_roles}"); raise KeyError(f"Missing roles: {missing_roles}")
        logging.info(f"Successfully loaded {len(roles)} roles from {filepath}")
        return roles
    except json.JSONDecodeError as e: logging.error(f"Error decoding JSON from {filepath}: {e}"); raise
    except Exception as e: logging.error(f"Unexpected error loading roles {filepath}: {e}"); raise

# --- Ollama API Interaction (More Robust) ---
def call_ollama_role(system_prompt, user_message, model_name, context_messages=None, temperature=0.7, top_p=0.9, format_json=False):
    """Sends request to Ollama API with retries, context warning, and error handling."""
    messages = []; payload = {}; last_exception = None
    if system_prompt: messages.append({"role": "system", "content": system_prompt})
    if context_messages: messages.extend(context_messages)
    messages.append({"role": "user", "content": user_message})
    payload = { "model": model_name, "messages": messages, "stream": False, "options": { "temperature": temperature, "top_p": top_p } }
    if format_json: payload["format"] = "json"
    estimated_chars = sum(len(msg.get("content", "")) for msg in messages)
    logging.debug(f"Attempting API call to {model_name}. Est. payload chars: ~{estimated_chars}.")
    if estimated_chars > CONTEXT_SIZE_WARNING_THRESHOLD: logging.warning(f"Estimated context size (~{estimated_chars} chars) exceeds threshold ({CONTEXT_SIZE_WARNING_THRESHOLD}).")
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(OLLAMA_API_URL, json=payload, timeout=API_TIMEOUT)
            response.raise_for_status()
            response_data = response.json(); message_content = response_data.get('message', {}).get('content', '')
            # Check for empty content *after* successful response
            if not message_content:
                logging.warning(f"Ollama returned empty message content (attempt {attempt + 1}/{MAX_RETRIES}).")
                last_exception = ValueError("Ollama returned empty message content")
                if attempt < MAX_RETRIES - 1: time.sleep(RETRY_DELAY * (attempt + 1)); continue
                else: logging.error("Ollama returned empty message content after max retries."); return None
            logging.debug(f"API call successful. Response length: {len(message_content)} chars."); return message_content.strip()
        except requests.exceptions.Timeout as e: logging.warning(f"API timeout (attempt {attempt + 1}/{MAX_RETRIES}): {e}"); last_exception = e
        except requests.exceptions.ConnectionError as e: logging.warning(f"API connection error (attempt {attempt + 1}/{MAX_RETRIES}): {e}"); last_exception = e
        except requests.exceptions.HTTPError as e: 
            logging.warning(f"HTTP error {e.response.status_code} (attempt {attempt + 1}/{MAX_RETRIES}): {e.response.text[:500]}...") 
            last_exception = e
        except requests.exceptions.RequestException as e: 
            logging.warning(f"General request error (attempt {attempt + 1}/{MAX_RETRIES}): {e}") 
            last_exception = e
        except json.JSONDecodeError as e: 
            logging.warning(f"JSON decode error (attempt {attempt + 1}/{MAX_RETRIES}): {e}") 
            last_exception = e
            if format_json: 
                logging.error("LLM failed JSON format.") 
                return None
        if attempt < MAX_RETRIES - 1: 
            wait_time = RETRY_DELAY * (attempt + 1) 
            logging.info(f"Retrying in {wait_time}s...") 
            time.sleep(wait_time)
        else: 
            logging.error(f"API call failed permanently after {MAX_RETRIES} retries. Last error: {type(last_exception).__name__}: {last_exception}") 
            return None

# --- Helper to save intermediate files ---
def save_intermediate_file(content, scene_num, file_type, revision_count):
    """Saves intermediate outputs into the unique run directory."""
    global unique_run_dir; filename = ""; filepath = ""
    if unique_run_dir is None: logging.error("Cannot save intermediate file - unique run directory not set."); return
    if content is None: logging.debug(f"Skipping save for {file_type} scene {scene_num} rev {revision_count} due to None content."); return
    # Determine filename using constants
    if file_type == "scene_plan": filename = PLAN_FILENAME
    elif file_type == "original_draft_plain": filename = ORIGINAL_DRAFT_PLAINTEXT_FILENAME
    elif isinstance(scene_num, int): filename = f"scene_{scene_num:03d}_{file_type}_rev_{revision_count}.txt"
    else: filename = f"{file_type}.txt" # For non-scene specific files like metadata (though metadata has its own name)
    filepath = os.path.join(unique_run_dir, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            if isinstance(content, (list, dict)): json.dump(content, f, indent=4)
            else: f.write(str(content)) # Ensure content is string
        logging.debug(f"Saved intermediate file: {filepath}")
    except (IOError, OSError, TypeError) as e: logging.error(f"Failed to save intermediate file {filepath}: {e}")

# --- Function to Load Scene Plan from JSON File ---
def load_scene_plan_from_json(plan_filepath):
    """Loads scene outlines from the specified JSON file."""
    logging.info(f"Attempting to load scene plan from: {plan_filepath}")
    if not os.path.exists(plan_filepath): logging.error(f"Scene plan JSON file not found: {plan_filepath}"); return None
    try:
        with open(plan_filepath, 'r', encoding='utf-8') as f: plan_data = json.load(f)
        if not isinstance(plan_data, list): logging.error(f"Scene plan file not list. Type: {type(plan_data)}"); return None
        scene_outlines = []
        for i, item in enumerate(plan_data):
            if not isinstance(item, dict) or len(item) != 1: logging.error(f"Item {i+1} in plan is not a single-key dict."); return None
            key = list(item.keys())[0]; value = item[key]
            if not isinstance(value, str) or not value.strip(): logging.error(f"Outline for Scene {i+1} (key '{key}') is not a non-empty string."); return None
            scene_outlines.append(value.strip())
        if not scene_outlines: logging.error("No outlines extracted from plan file."); return None
        logging.info(f"Successfully loaded {len(scene_outlines)} scene outlines from {plan_filepath}.")
        return scene_outlines
    except json.JSONDecodeError as e: logging.error(f"Failed to decode JSON plan file {plan_filepath}: {e}"); return None
    except Exception as e: logging.error(f"Unexpected error processing plan file {plan_filepath}: {e}"); return None

# --- Resume State Handling ---
def save_resume_state(state_data):
    """Saves the current state to the resume file."""
    global unique_run_dir
    if unique_run_dir is None: logging.error("Cannot save resume state - unique run directory not set."); return False
    state_filepath = os.path.join(unique_run_dir, RESUME_STATE_FILENAME); temp_filepath = state_filepath + ".tmp"
    try:
        with open(temp_filepath, 'w', encoding='utf-8') as f: json.dump(state_data, f, indent=4)
        os.replace(temp_filepath, state_filepath); logging.info(f"Resume state saved successfully to {state_filepath}"); return True
    except (IOError, OSError, TypeError, json.JSONDecodeError) as e:
        logging.error(f"Failed to save resume state to {state_filepath}: {e}")
        if os.path.exists(temp_filepath): 
            try: 
                os.remove(temp_filepath) 
            except OSError: 
                pass
        return False

def load_resume_state(resume_dir):
    """Loads the state from a resume file in the specified directory."""
    state_filepath = os.path.join(resume_dir, RESUME_STATE_FILENAME)
    logging.info(f"Attempting to load resume state from: {state_filepath}")
    if not os.path.exists(state_filepath): logging.error(f"Resume state file not found: {state_filepath}"); return None
    try:
        with open(state_filepath, 'r', encoding='utf-8') as f: state_data = json.load(f)
        required_keys = ["last_approved_scene_number", "unique_run_dir", "model_name", "draft_filepath", "plan_filepath", "scene_plans", "approved_scenes_data", "start_timestamp"] # Added start_timestamp
        if not all(key in state_data for key in required_keys): logging.error(f"Resume state file missing keys."); return None
        if state_data.get("unique_run_dir") != resume_dir: logging.warning(f"Resume state directory mismatch!"); state_data["unique_run_dir"] = resume_dir
        if not isinstance(state_data.get("approved_scenes_data"), list): logging.error("Resume state 'approved_scenes_data' not list."); return None
        logging.info(f"Resume state loaded successfully. Last approved scene: {state_data['last_approved_scene_number']}")
        return state_data
    except json.JSONDecodeError as e: logging.error(f"Failed to decode JSON resume state file {state_filepath}: {e}"); return None
    except Exception as e: logging.error(f"Unexpected error loading resume state file {state_filepath}: {e}"); return None

# --- Enhanced Logging Function ---
def log_step(step_name, scene_num=None, rev_count=None, extra_info=""):
    """Provides formatted logging for steps."""
    prefix = f"--- [Scene {scene_num:03d} Rev {rev_count}]" if scene_num and rev_count else "--- [Setup]" if scene_num is None else f"--- [Scene {scene_num:03d}]"
    message = f"{prefix} {step_name} ---";
    if extra_info: message += f" ({extra_info})"
    logging.info(message)

# --- Context Building Helper ---
def build_historical_context(approved_scenes_data, num_full, num_summary=None):
    """Builds context string with full text for recent scenes and summaries for older ones."""
    context_parts = []; num_approved = len(approved_scenes_data)
    full_text_start_index = max(0, num_approved - num_full); summary_end_index = full_text_start_index
    summary_start_index = 0 if num_summary is None else max(0, summary_end_index - num_summary)
    # Add recent full texts
    if full_text_start_index < num_approved:
        context_parts.append("--- Recent Scene Context (Full Text) ---")
        for i in range(full_text_start_index, num_approved):
            scene_data = approved_scenes_data[i]; context_parts.append(f"Scene {scene_data['scene_num']}:\n{scene_data['full_text']}\n")
    # Add older summaries
    if summary_start_index < summary_end_index:
        context_parts.append("--- Older Scene Context (Summaries) ---")
        for i in range(summary_start_index, summary_end_index):
             scene_data = approved_scenes_data[i]; summary_text = scene_data.get('summary', f"[Summary missing for Scene {scene_data['scene_num']}]")
             context_parts.append(f"Scene {scene_data['scene_num']} Summary:\n{summary_text}\n")
    return "\n".join(context_parts) if context_parts else "No previous approved scenes available."

# --- Failed Scene Archiver ---
def archive_failed_scene(scene_num):
    """Copies all intermediate files for a failed scene to an archive folder."""
    global unique_run_dir
    if unique_run_dir is None: return
    failed_archive_base_dir = os.path.join(unique_run_dir, "_failed_scenes")
    failed_scene_dir = os.path.join(failed_archive_base_dir, f"scene_{scene_num:03d}")
    try:
        os.makedirs(failed_scene_dir, exist_ok=True)
        logging.info(f"Archiving files for failed Scene {scene_num} to: {failed_scene_dir}")
        scene_file_prefix = f"scene_{scene_num:03d}_"
        copied_count = 0; error_count = 0
        for filename in os.listdir(unique_run_dir):
            if filename.startswith(scene_file_prefix) and os.path.isfile(os.path.join(unique_run_dir, filename)):
                source_path = os.path.join(unique_run_dir, filename)
                dest_path = os.path.join(failed_scene_dir, filename)
                try: shutil.copy2(source_path, dest_path); copied_count += 1
                except (IOError, OSError, shutil.Error) as e: logging.error(f"Failed to copy {filename} to archive: {e}"); error_count += 1
        logging.info(f"Copied {copied_count} files to archive for failed Scene {scene_num}. {error_count} errors occurred.")
    except OSError as e: logging.error(f"Failed to create archive directory {failed_scene_dir}: {e}")

# --- Main Workflow ---
def main(args):
    """Orchestrates the story REWRITING process with resume and summarization."""
    global unique_run_dir
    global num_scenes_to_generate

    # --- Determine Run Mode & Setup Directories/Logging ---
    resume_state = None; run_mode = ""; log_mode = 'w'; model_name=""
    draft_filepath=""; plan_filepath=""; scene_plans = None
    approved_scenes_data = []; last_approved_scene_number = 0; start_scene_num = 1
    total_approved_count = 0; total_failed_count = 0
    run_start_timestamp = datetime.datetime.now().isoformat() # Capture start time early

    if args.resume:
        if not os.path.isdir(args.resume): print(f"ERROR: Resume directory not found: {args.resume}"); sys.exit(1)
        resume_state = load_resume_state(args.resume)
        if resume_state is None: print(f"ERROR: Failed to load resume state from {args.resume}."); sys.exit(1)
        unique_run_dir = args.resume
        model_name = resume_state['model_name']
        draft_filepath = resume_state['draft_filepath']
        plan_filepath = resume_state['plan_filepath']
        scene_plans = resume_state['scene_plans']
        approved_scenes_data = resume_state['approved_scenes_data']
        last_approved_scene_number = resume_state['last_approved_scene_number']
        start_scene_num = last_approved_scene_number + 1
        num_scenes_to_generate = len(scene_plans)
        total_approved_count = last_approved_scene_number
        run_start_timestamp = resume_state.get("start_timestamp", run_start_timestamp) # Use original start time if available
        log_mode = 'a'; run_mode = "Resuming Run"
    elif args.draft_file and args.plan_file:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_run_dir = os.path.join(BASE_OUTPUT_DIR, f"rewrite_{timestamp}")
        try: os.makedirs(unique_run_dir, exist_ok=True); print(f"Output will be saved to: {unique_run_dir}")
        except OSError as e: print(f"CRITICAL ERROR: Failed to create output directory {unique_run_dir}: {e}"); sys.exit(1)
        model_name = args.model
        draft_filepath = args.draft_file; plan_filepath = args.plan_file
        log_mode = 'w'; run_mode = "Starting New Run"
        scene_plans = load_scene_plan_from_json(plan_filepath)
        if scene_plans is None: print(f"ERROR: Failed to load scene plan from {plan_filepath}."); sys.exit(1)
        num_scenes_to_generate = len(scene_plans)
    else: print("ERROR: Use --new or --resume."); sys.exit(1)

    log_file = os.path.join(unique_run_dir, LOG_FILENAME)
    for handler in logging.root.handlers[:]: logging.root.removeHandler(handler)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s', handlers=[logging.FileHandler(log_file, mode=log_mode, encoding='utf-8'), logging.StreamHandler()])
    logging.info(f"--- {run_mode} ---")
    logging.info(f"Output Dir: {unique_run_dir}")
    logging.info(f"Draft: {draft_filepath}, Plan: {plan_filepath}, Model: {model_name}")
    logging.info(f"Total scenes in plan: {num_scenes_to_generate}")
    logging.info(f"Keeping full text for last {NUM_FULL_TEXT_CONTEXT_SCENES} approved scenes.")
    if run_mode == "Resuming Run": logging.info(f"Resuming from Scene {start_scene_num}.")

    # --- Load Roles & Original Draft ---
    log_step("Loading Roles & Draft", scene_num=None)
    script_start_time = time.time() # Track execution time
    try: llm_roles = load_roles()
    except Exception as e: logging.critical(f"FATAL: Failed loading roles: {e}"); return

    original_draft_text = None
    original_draft_plain_path = os.path.join(unique_run_dir, ORIGINAL_DRAFT_PLAINTEXT_FILENAME)
    if os.path.exists(original_draft_plain_path):
        try:
            with open(original_draft_plain_path, 'r', encoding='utf-8') as f: original_draft_text = f.read()
            logging.info("Loaded existing plain text original draft.")
        except Exception as e: 
            logging.error(f"Failed loading saved plain draft: {e}. Re-converting.")
            original_draft_text = None
    if original_draft_text is None:
        original_draft_text = load_rtf_as_text(draft_filepath)
        if original_draft_text is None: 
            logging.critical(f"FATAL: Failed loading draft: {draft_filepath}.") 
            return
        save_intermediate_file(original_draft_text, None, "original_draft_plain", 0)

    original_draft_word_count = len(original_draft_text.split())
    logging.info(f"Original draft context ready (~{original_draft_word_count} words).")

    # --- Save Initial/Loaded State ---
    current_state = {
        "last_approved_scene_number": last_approved_scene_number, "unique_run_dir": unique_run_dir,
        "model_name": model_name, "draft_filepath": draft_filepath, "plan_filepath": plan_filepath,
        "scene_plans": scene_plans, "approved_scenes_data": approved_scenes_data,
        "start_timestamp": run_start_timestamp # Save start time
    }
    if not save_resume_state(current_state): logging.warning("Failed to save initial/loaded resume state.")
    if run_mode == "Starting New Run": save_intermediate_file(scene_plans, None, "scene_plan", 0)

    # --- Scene Rewrite Loop ---
    story_context = {
        "summary": STORY_SUMMARY, "approved_scenes_data": approved_scenes_data,
        "themes": "Heroism, Found Family, Strategy vs Brute Force, Ancient Lore",
        "world_notes": "Medieval fantasy Eldoria, Firepeak Mountains (dangerous), subtle magic influencing minds, political alliances matter."
    }
    full_scene_plan_text = "\n".join([f"Scene {i+1}: {plan}" for i, plan in enumerate(scene_plans)])

    progress_bar = tqdm(range(start_scene_num, num_scenes_to_generate + 1),
                        initial=last_approved_scene_number, total=num_scenes_to_generate,
                        desc="Rewriting Scenes", unit="scene", dynamic_ncols=True) # dynamic_ncols helps resizing

    for scene_num in progress_bar:
        progress_bar.set_description(f"Scene {scene_num}/{num_scenes_to_generate}")
        log_step(f"Starting Scene {scene_num}/{num_scenes_to_generate}", scene_num=scene_num, rev_count=0)
        scene_plan_outline = scene_plans[scene_num - 1]
        logging.info(f"Scene Plan Outline: {scene_plan_outline}")

        current_draft = None; initial_critique = "No critique generated."; synthesized_critique = "No critique generated."
        scene_approved = False; revision_count = 0; abort_scene = False
        historical_context = build_historical_context(story_context["approved_scenes_data"], NUM_FULL_TEXT_CONTEXT_SCENES)

        while not scene_approved and revision_count < MAX_REVISIONS_PER_SCENE and not abort_scene:
            revision_count += 1; log_step(f"Revision Cycle {revision_count}", scene_num=scene_num, rev_count=revision_count)

            # --- Step 1: Initial Rewrite ---
            if revision_count == 1:
                log_step("[Writer] Initial Rewrite", scene_num=scene_num, rev_count=revision_count)
                writer_task = f"Rewrite Scene {scene_num} based on plan.\n**Plan:** {scene_plan_outline}\n\nTask: Write new scene fulfilling plan. Use 'Original Draft Context' as inspiration.\n\nSummary:\n{story_context['summary']}\n\nPrev Rewritten Scenes Context:\n{historical_context}\n\n--- Original Draft Context ---\n{original_draft_text}\n--- End Original Draft ---"
                draft_1 = call_ollama_role(llm_roles['PrimaryWriter']['system_prompt'], writer_task, model_name)
                if draft_1 is None: logging.error(f"CRITICAL: Writer failed initial rewrite Scene {scene_num}. Aborting scene."); abort_scene = True; continue
                current_draft = draft_1; save_intermediate_file(current_draft, scene_num, "draft_1_initial_rewrite", revision_count)
            else: logging.info(f"[Loop] Using previous cycle's Draft 3 for Scene {scene_num} Rev {revision_count}")

            # --- Steps 2-6 ---
            critique_source = "";
            if revision_count == 1:
                log_step("[Critiquer] Initial Critique", scene_num=scene_num, rev_count=revision_count)
                critiquer_task_initial = f"Initial critique Scene {scene_num}.\nPlan: {scene_plan_outline}\nSummary:\n{story_context['summary']}\n\nDraft:\n{current_draft}\n\nTask: Critique vs plan, quality. ID 1-3 KEY areas."
                initial_critique = call_ollama_role(llm_roles['CriticalEditor']['system_prompt'], critiquer_task_initial, model_name); initial_critique = initial_critique or "Critique failed."
                save_intermediate_file(initial_critique, scene_num, "critique_initial", revision_count); critique_source = initial_critique
            else: log_step("[Loop] Using synthesized critique", scene_num=scene_num, rev_count=revision_count); critique_source = synthesized_critique
            log_step("[Rewriter] Rewrite based on critique", scene_num=scene_num, rev_count=revision_count)
            if not critique_source or critique_source == "No critique generated.": logging.warning("No valid critique for Rewriter."); rewriter_task = f"Rewrite Scene {scene_num} draft for quality & plan adherence.\nPlan: {scene_plan_outline}\nDraft:\n{current_draft}"
            else: rewriter_task = f"Rewrite Scene {scene_num} based on critique & plan.\nPlan: {scene_plan_outline}\nCritique:\n{critique_source}\nDraft:\n{current_draft}"
            draft_2 = call_ollama_role(llm_roles['FocusedRewriter']['system_prompt'], rewriter_task, model_name); draft_2 = draft_2 or current_draft
            save_intermediate_file(draft_2, scene_num, "draft_2_rewritten", revision_count)
            log_step("[Writer] Revision pass", scene_num=scene_num, rev_count=revision_count)
            writer_revision_task = f"Revise Scene {scene_num}.\nIntegrate Rewriter draft (Draft 2), align with vision, flow, style, plan.\nPlan: {scene_plan_outline}\nCritique:\n{critique_source}\nDraft 2:\n{draft_2}\nOutput Draft 3."
            draft_3 = call_ollama_role(llm_roles['PrimaryWriter']['system_prompt'], writer_revision_task, model_name); draft_3 = draft_3 or draft_2
            current_draft = draft_3; save_intermediate_file(current_draft, scene_num, "draft_3_revised", revision_count)
            log_step("[Specialists] Running checks", scene_num=scene_num, rev_count=revision_count)
            specialist_reports = {}; specialist_failed = False
            consistency_context_str = build_historical_context(story_context["approved_scenes_data"], NUM_FULL_TEXT_CONTEXT_SCENES);
            consistency_task = f"Check rewritten Scene {scene_num} draft consistency.\nCurrent Plan: {scene_plan_outline}\nFull Plan:\n{full_scene_plan_text}\nPrev Scenes:\n{consistency_context_str}\nWorld/Summary:\n{story_context['world_notes']}\n{story_context['summary']}\n\nCurrent Draft:\n{current_draft}\n\nReport inconsistencies or 'Passed.'"
            consistency_report = call_ollama_role(llm_roles['ConsistencyChecker']['system_prompt'], consistency_task, model_name); specialist_reports['Consistency'] = consistency_report or "Failed"; save_intermediate_file(consistency_report, scene_num, "report_consistency", revision_count); specialist_failed = specialist_failed or (consistency_report is None)
            dialogue_task = f"Analyze dialogue Scene {scene_num} draft.\nDraft 3:\n{current_draft}\n\nFeedback or 'Passed.'"
            dialogue_report = call_ollama_role(llm_roles['DialogueDoctor']['system_prompt'], dialogue_task, model_name); specialist_reports['Dialogue'] = dialogue_report or "Failed"; save_intermediate_file(dialogue_report, scene_num, "report_dialogue", revision_count); specialist_failed = specialist_failed or (dialogue_report is None)
            pacing_task = f"Analyze pacing Scene {scene_num} draft.\nDraft 3:\n{current_draft}\n\nFeedback or 'Passed.'"
            pacing_report = call_ollama_role(llm_roles['PacingTensionAnalyst']['system_prompt'], pacing_task, model_name); specialist_reports['PacingTension'] = pacing_report or "Failed"; save_intermediate_file(pacing_report, scene_num, "report_pacing", revision_count); specialist_failed = specialist_failed or (pacing_report is None)
            if specialist_failed: logging.warning("One or more specialist checks failed.")
            log_step("[Critiquer] Final Synthesis & Approval", scene_num=scene_num, rev_count=revision_count)
            reports_text = "\n".join([f"--- {rtype} Report ---\n{report}" for rtype, report in specialist_reports.items() if report and not report.strip().endswith("Passed.") and not report.strip().endswith("Failed")]); reports_text = reports_text.strip() if reports_text.strip() else "No specific issues."
            final_critique_task = f"Final decision Scene {scene_num}, Rev {revision_count}.\nReview draft, plan, reports.\nPlan: {scene_plan_outline}\nSummary:\n{story_context['summary']}\n\nDraft 3:\n{current_draft}\n\nReports Summary:\n{reports_text}\n\nDecision: 'Approved' or 'Needs More Work'? If Needs More Work, give concise critique (1-3 points)."
            approval_decision = call_ollama_role(llm_roles['CriticalEditor']['system_prompt'], final_critique_task, model_name)
            if approval_decision is None: logging.error(f"CRITICAL: Final Critiquer eval failed Scene {scene_num} Rev {revision_count}. Assuming 'Needs More Work'."); approval_decision = f"Needs More Work: Final critique failed."
            logging.info(f"Critiquer Decision: {approval_decision.splitlines()[0]}")

            # Step 7: Check Approval, Summarize, Save State, Loop
            if approval_decision.strip().startswith("Approved"):
                log_step("Scene APPROVED", scene_num=scene_num, rev_count=revision_count)
                scene_approved = True; total_approved_count += 1
                log_step("Summarizing Approved Scene", scene_num=scene_num, rev_count=revision_count)
                summary_task = f"Create a concise summary (3-5 sentences) of the following scene text, focusing on plot events, character state changes, crucial info revealed, and object/location status for continuity:\n\n{current_draft}"
                scene_summary = call_ollama_role(llm_roles['SceneSummarizer']['system_prompt'], summary_task, model_name); scene_summary = scene_summary or f"[Summary failed Scene {scene_num}]"
                save_intermediate_file(scene_summary, scene_num, "summary", revision_count)
                new_scene_data = { "scene_num": scene_num, "full_text": current_draft, "summary": scene_summary }
                approved_scenes_data.append(new_scene_data); story_context["approved_scenes_data"] = approved_scenes_data; last_approved_scene_number = scene_num
                current_state = {
                    "last_approved_scene_number": last_approved_scene_number, "unique_run_dir": unique_run_dir,
                    "model_name": model_name, "draft_filepath": draft_filepath, "plan_filepath": plan_filepath,
                    "scene_plans": scene_plans, "approved_scenes_data": approved_scenes_data, "start_timestamp": run_start_timestamp
                }
                if not save_resume_state(current_state): logging.error("CRITICAL: Failed to save resume state after approval!")
                final_filename = f"scene_{scene_num:03d}_final_rev_{revision_count}.txt"
                try: 
                    with open(os.path.join(unique_run_dir, final_filename), "w", encoding="utf-8") as f: 
                        f.write(current_draft) 
                    logging.info(f"Saved final approved scene: {final_filename}")
                except (IOError, OSError) as e: 
                    logging.error(f"Failed to save final scene file {final_filename}: {e}")
            else:
                synthesized_critique = approval_decision.replace("Needs More Work:", "").strip(); synthesized_critique = synthesized_critique or "General improvements needed."
                save_intermediate_file(synthesized_critique, scene_num, "critique_synthesized", revision_count)
                log_step("Scene Needs More Work", scene_num=scene_num, rev_count=revision_count, extra_info=f"Critique: {synthesized_critique[:100]}...")

        # --- End of revision loop ---
        if abort_scene: logging.error(f"Scene {scene_num} processing ABORTED."); total_failed_count += 1
        elif not scene_approved:
            logging.warning(f"Scene {scene_num} FAILED APPROVAL after {MAX_REVISIONS_PER_SCENE} revisions."); total_failed_count += 1
            save_intermediate_file(current_draft, scene_num, "unapproved_final_draft", MAX_REVISIONS_PER_SCENE)
            archive_failed_scene(scene_num) # Archive the failed scene's files

    # --- End of all scene processing ---
    progress_bar.close()
    script_end_time = time.time(); total_script_time = script_end_time - script_start_time
    run_end_timestamp = datetime.datetime.now().isoformat()
    logging.info("\n" + "="*20 + " Story Rewriting Finished " + "="*20)
    logging.info(f"Total processing time: {total_script_time:.2f} seconds ({total_script_time/60:.2f} minutes).")
    logging.info(f"Scenes Approved: {total_approved_count}/{num_scenes_to_generate}")
    logging.info(f"Scenes Failed: {total_failed_count}/{num_scenes_to_generate}")

    # --- Create Metadata File ---
    metadata = {
        "run_type": run_mode,
        "start_timestamp": run_start_timestamp, # Use consistent start time
        "end_timestamp": run_end_timestamp,
        "total_duration_seconds": round(total_script_time, 2),
        "model_used": model_name,
        "original_draft_file": draft_filepath,
        "scene_plan_file": plan_filepath,
        "total_scenes_in_plan": num_scenes_to_generate,
        "scenes_approved": total_approved_count,
        "scenes_failed_approval": total_failed_count,
        "max_revisions_per_scene": MAX_REVISIONS_PER_SCENE,
        "num_full_text_context": NUM_FULL_TEXT_CONTEXT_SCENES,
        "output_directory": unique_run_dir,
        "config_settings": {s: dict(config.items(s)) for s in config.sections()}
    }
    metadata_filepath = os.path.join(unique_run_dir, "run_metadata.json")
    try:
        with open(metadata_filepath, "w", encoding="utf-8") as f: json.dump(metadata, f, indent=4)
        logging.info(f"Run metadata saved to: {metadata_filepath}")
    except (IOError, OSError, TypeError) as e: logging.error(f"Failed to save metadata file: {e}")

    # --- Final Story Output ---
    final_story_text = f"Original Draft Source: {draft_filepath}\nScene Plan Source: {plan_filepath}\nModel Used: {model_name}\n"
    final_story_text += f"Run Start: {run_start_timestamp}\nRun End: {run_end_timestamp}\n" # Add timestamps
    final_story_text += f"High-Level Summary:\n{STORY_SUMMARY}\n\n" + "=" * 60 + "\n\n"
    if approved_scenes_data: final_story_text += f"Generated {len(approved_scenes_data)} Approved Scenes (out of {num_scenes_to_generate} planned):\n\n"; final_story_text += "\n\n".join([f"--- Scene {scene_data['scene_num']} ---\n\n{scene_data['full_text']}\n\n" + "=" * 60 for scene_data in approved_scenes_data])
    else: final_story_text += f"No scenes were successfully approved ({num_scenes_to_generate} planned)."
    final_output_path = os.path.join(unique_run_dir, FINAL_STORY_FILENAME)
    try: 
        with open(final_output_path, "w", encoding="utf-8") as f: 
            f.write(final_story_text) 
        logging.info(f"Final rewritten story saved to: {final_output_path}")
    except (IOError, OSError) as e: 
        logging.error(f"CRITICAL FAILURE: Error saving final story file {final_output_path}: {e}")
    logging.info(f"Process complete. Check the '{unique_run_dir}' directory.")


# --- Script Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rewrite story draft using scene plan & multi-LLM workflow with resume & summarization.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--new", nargs=2, metavar=('DRAFT_FILE', 'PLAN_FILE'), help="Start a new rewrite run. Provide: draft.rtf plan.json")
    group.add_argument("--resume", metavar='RUN_DIRECTORY', help="Resume a previous run from the specified directory.")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL_CONFIG, help=f"Ollama model for new run (default from config: {DEFAULT_MODEL_CONFIG})")

    args = parser.parse_args()
    main_args = argparse.Namespace()

    if args.resume:
        main_args.resume = args.resume; main_args.new = None; main_args.model = None
        main_args.draft_file = None; main_args.plan_file = None
    elif args.new:
        main_args.resume = None; main_args.draft_file = args.new[0]; main_args.plan_file = args.new[1]; main_args.model = args.model
        if not os.path.exists(main_args.draft_file): print(f"ERROR: Draft file not found: {main_args.draft_file}"); sys.exit(1)
        if not os.path.exists(main_args.plan_file): print(f"ERROR: Plan file not found: {main_args.plan_file}"); sys.exit(1)
    else: print("ERROR: Use --new or --resume."); sys.exit(1) # Should be caught by argparse

    # Final check before starting main logic
    if not os.path.exists(ROLES_FILE):
        print(f"ERROR: Roles file '{ROLES_FILE}' not found. Please ensure it exists.")
        sys.exit(1)

    main(main_args)

    # python3 story_generator.py --new mybook.rtf scenes.json