import requests
import json
import os
import argparse
import logging
import time
import datetime # Added for timestamp
# import concurrent.futures # Keep commented unless implementing parallelism

# --- Configuration ---
OLLAMA_API_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "gemma3:27b" # Or choose another powerful model
ROLES_FILE = "llm_roles.json"
MAX_REVISIONS_PER_SCENE = 10 # Adjust as needed
BASE_OUTPUT_DIR = "story_output_planned_robust" # Renamed to BASE_
RETRY_DELAY = 5 # Seconds to wait before retrying API call
MAX_RETRIES = 3 # Max retries for API calls
API_TIMEOUT = 900 # Seconds before API call times out

# --- Hardcoded Story Summary ---
STORY_SUMMARY = """
In life, Kaelen was a legend in the digital realms—a peerless gamer obsessed with the secrets that lay behind every quest, every puzzle, every hidden piece of lore. But death, as Kaelen soon discovers, holds secrets greater still.

When Kaelen awakens in a world not his own, he finds himself transformed—trapped within the walls of the sentient library known as the Echo Atheneum. Shelved among ancient tomes filled with magic deemed forbidden by the oppressive regime of the Iron Church, Kaelen now exists as an intangible consciousness. He cannot leave, cannot touch, but he can speak through the fluttering of pages and the whispered rustling of ink upon parchment.

The Atheneum, hidden beneath the crumbling city of Verenhal, becomes a refuge for scholars and adventurers brave enough to seek truths outlawed by the Church. But Kaelen soon learns that his new existence has a deeper purpose: to uncover the world's hidden truths—truths about magic's true origin, the disappearance of the old gods, and the dark corruption festering in the heart of Verenhal itself. Only by leading seekers toward these revelations can Kaelen regain a physical form and claim redemption.

Guided by fragments of memories and hints found within the forbidden books themselves, Kaelen allies with a group of young adventurers led by Seris—a fiercely intelligent young woman and former apprentice to an Iron Church inquisitor. Determined, sharp, and burdened by past betrayals, Seris alone suspects the library's true nature. Yet as she delves deeper into forbidden lore, Kaelen's whispered truths become her only guidance, setting in motion a fragile bond built on trust and secrets.

Romance blooms slowly, softly, threaded through late-night conversations carried in quiet echoes and shared discoveries. Seris and Kaelen find solace in one another's minds, a profound connection that defies Kaelen's incorporeal limitations. But the Iron Church's inquisitors are relentless, hunting those who question doctrine, destroying those who defy their laws. When Seris's identity and purpose become dangerously entangled in Verenhal's shadowy politics, Kaelen must confront a choice: sacrifice his chance at humanity for the woman who reawakened his heart, or risk everything to reclaim a life worth living.

As truth unfolds, Kaelen and Seris discover magic is not forbidden merely for power—but because it contains memories the world itself wishes forgotten. Memories that, if revealed, could change or break their world forever.

In this epic tale of discovery, courage, forbidden knowledge, and quiet, poignant romance, Kaelen learns that truth—like magic—is a dangerous and beautiful force, capable of reshaping worlds and hearts alike.
"""

# --- Logging Setup ---
# Logging will initially be set up relative to the BASE output dir,
# then the directory will be renamed at the end.
initial_log_dir = BASE_OUTPUT_DIR # Use the base name initially
log_file = os.path.join(initial_log_dir, 'story_generator.log')
if not os.path.exists(initial_log_dir):
    try:
        os.makedirs(initial_log_dir)
    except OSError as e:
        # If initial creation fails, log to current dir as fallback
        initial_log_dir = '.' # Fallback
        log_file = 'story_generator.log'
        print(f"Error creating base output directory {BASE_OUTPUT_DIR}: {e}. Logging to current directory.")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# --- Role Loading ---
def load_roles(filepath=ROLES_FILE):
    """Loads the LLM role prompts from a JSON file with error handling."""
    if not os.path.exists(filepath):
        logging.error(f"Role configuration file not found: {filepath}")
        raise FileNotFoundError(f"Role configuration file not found: {filepath}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            roles = json.load(f)
        # *** Check if StoryPlanner role exists after loading ***
        if "StoryPlanner" not in roles:
             logging.error(f"FATAL: 'StoryPlanner' role not found in {filepath}. Please add it.")
             raise KeyError("'StoryPlanner' role not found.")
        logging.info(f"Successfully loaded {len(roles)} roles from {filepath}")
        return roles
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {filepath}: {e}")
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading {filepath}: {e}")
        raise

# --- Ollama API Interaction (More Robust) ---
# (Keep the robust call_ollama_role function from the previous version)
def call_ollama_role(system_prompt, user_message, model_name, context_messages=None, temperature=0.7, top_p=0.9, format_json=False):
    """Sends a request to the Ollama API with retries and robust error handling."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if context_messages:
         messages.extend(context_messages)
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": top_p
        }
    }
    # Force JSON format ONLY if the specific role prompt requires it
    if format_json:
         payload["format"] = "json"

    logging.debug(f"Attempting API call to {model_name}. Payload size: ~{len(json.dumps(payload)) / 1024:.1f} KB.")

    last_exception = None
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(OLLAMA_API_URL, json=payload, timeout=API_TIMEOUT) # Use configured timeout
            response.raise_for_status() # Checks for 4xx/5xx errors

            response_data = response.json()
            message_content = response_data.get('message', {}).get('content', '')

            if not message_content:
                 logging.warning(f"Ollama returned empty message (attempt {attempt + 1}/{MAX_RETRIES}).")
                 last_exception = ValueError("Ollama returned empty message") # Store error type
                 if attempt < MAX_RETRIES - 1:
                     time.sleep(RETRY_DELAY * (attempt + 1))
                     continue
                 else:
                     logging.error("Ollama returned empty message after max retries.")
                     return None # Permanent failure after retries

            # Success!
            logging.debug(f"API call successful. Response length: {len(message_content)} chars.")
            return message_content.strip()

        # Specific Requests exceptions
        except requests.exceptions.Timeout as e:
            logging.warning(f"API call timed out (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            last_exception = e
        except requests.exceptions.ConnectionError as e:
            logging.warning(f"API connection error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            last_exception = e
        except requests.exceptions.HTTPError as e:
            logging.warning(f"HTTP error {e.response.status_code} (attempt {attempt + 1}/{MAX_RETRIES}): {e.response.text[:500]}...")
            last_exception = e
        except requests.exceptions.RequestException as e:
            logging.warning(f"General request error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            last_exception = e
        # JSON decoding error - specifically important if format='json' was used
        except json.JSONDecodeError as e:
             # If we requested JSON, this is a failure mode for the LLM not adhering to format
             logging.warning(f"Failed to decode Ollama JSON response (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
             if 'response' in locals() and response is not None:
                logging.warning(f"Raw Response Text Snippet: {response.text[:500]}...")
             last_exception = e
             # No retry if JSON was specifically requested and failed - model didn't follow instructions
             if format_json:
                 logging.error("LLM failed to return valid JSON as requested.")
                 return None


        # Wait before retrying if it wasn't the last attempt and not a JSON format failure
        if attempt < MAX_RETRIES - 1:
            wait_time = RETRY_DELAY * (attempt + 1)
            logging.info(f"Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
        else:
            logging.error(f"API call failed permanently after {MAX_RETRIES} retries.")
            logging.error(f"Last encountered error: {type(last_exception).__name__}: {last_exception}")
            return None # Indicate permanent failure


# --- Helper to save intermediate files (More Robust) ---
def save_intermediate_file(content, scene_num, file_type, revision_count, output_dir): # Added output_dir parameter
    """Saves intermediate outputs with error handling."""
    if content is None:
        logging.debug(f"Skipping save for {file_type} scene {scene_num} rev {revision_count} due to None content.")
        return
    # Adjust filename slightly for planner output (no revision count)
    if file_type == "scene_plan":
        filename = "scene_plan_full.json"
        filepath = os.path.join(output_dir, filename) # Use passed output_dir
    elif isinstance(scene_num, int): # Normal scene processing
        filename = f"scene_{scene_num}_{file_type}_rev_{revision_count}.txt"
        filepath = os.path.join(output_dir, filename) # Use passed output_dir
    else: # Fallback or non-scene specific log
         filename = f"{file_type}.txt"
         filepath = os.path.join(output_dir, filename) # Use passed output_dir

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            # If content is list/dict, save as pretty JSON, else save as text
            if isinstance(content, (list, dict)):
                 json.dump(content, f, indent=4)
            else:
                 f.write(str(content)) # Ensure content is string
        logging.debug(f"Saved intermediate file: {filepath}")
    except (IOError, OSError, TypeError) as e:
        logging.error(f"Failed to save intermediate file {filepath}: {e}")


# --- Function to Generate Scene Plan (More Flexible Parsing) ---
def generate_scene_plan(llm_roles, model_name, num_scenes, output_dir): # Added output_dir
    """Calls the StoryPlanner LLM and flexibly parses the scene outlines."""
    logging.info(f"Generating scene plan for {num_scenes} scenes...")
    planner_prompt = llm_roles['StoryPlanner']['system_prompt']
    planner_user_message = (
        f"Please generate a scene-by-scene outline for a story with the following summary, breaking it into exactly {num_scenes} scenes.\n\n"
        f"Story Summary:\n{STORY_SUMMARY}\n\n"
        f"Number of Scenes: {num_scenes}\n\n"
        f"Output only the JSON list of strings as specified in the system prompt. Ensure the output starts with '[' and ends with ']'." # Added emphasis
    )

    # Request JSON format from Ollama for the planner
    plan_json_str = call_ollama_role(planner_prompt, planner_user_message, model_name, format_json=True)

    if plan_json_str is None:
        logging.error("StoryPlanner LLM failed to return a response.")
        return None

    try:
        parsed_data = json.loads(plan_json_str)
        scene_plans = None # Initialize

        # --- Flexible Parsing Logic ---
        if isinstance(parsed_data, list):
            # Ideal case: LLM returned a list directly
            scene_plans = parsed_data
            logging.info("StoryPlanner returned a JSON list directly.")
        elif isinstance(parsed_data, dict):
            logging.warning("StoryPlanner returned a JSON object instead of a list. Attempting to extract list...")
            # Check common keys where the list might be nested
            possible_keys = ["scenes", "plan", "outlines", "scene_outlines"]
            for key in possible_keys:
                if key in parsed_data and isinstance(parsed_data[key], list):
                    scene_plans = parsed_data[key]
                    logging.info(f"Successfully extracted scene list from object using key '{key}'.")
                    break # Found the list
            if scene_plans is None:
                logging.error(f"Could not find a list within the returned JSON object. Keys: {list(parsed_data.keys())}")
                return None # Failed to extract
        else:
            # The parsed data is neither a list nor a dict we can handle
            logging.error(f"StoryPlanner output was not a JSON list or a recognized dictionary structure. Type: {type(parsed_data)}, Output: {plan_json_str[:500]}...")
            return None
        # --- End Flexible Parsing Logic ---

        # --- Validation (runs on the extracted or direct list) ---
        if not isinstance(scene_plans, list):
             # This should theoretically not be reached if extraction logic is sound, but safety check
             logging.error("Internal Error: Failed to obtain a list after parsing/extraction.")
             return None

        actual_num_scenes = len(scene_plans) # Get the actual count from the list
        if actual_num_scenes != num_scenes:
            logging.warning(f"StoryPlanner returned {actual_num_scenes} outlines, but {num_scenes} were requested. Using the generated list ({actual_num_scenes} scenes). Check plan quality.")
            # No global adjustment needed here, we return the list, and the caller uses its length.

        if not all(isinstance(item, str) for item in scene_plans):
             logging.error(f"StoryPlanner list contains non-string elements. Check items: {scene_plans}")
             # Attempt to convert items to string? Or fail? Let's fail for now.
             # Example conversion (use with caution): scene_plans = [str(item) for item in scene_plans]
             return None

        logging.info(f"Successfully generated and validated scene plan with {actual_num_scenes} outlines.")
        save_intermediate_file(scene_plans, None, "scene_plan", 0, output_dir) # Pass output_dir
        return scene_plans # Return the validated list

    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode JSON scene plan from StoryPlanner: {e}")
        logging.error(f"Raw Planner Output: {plan_json_str[:1000]}...") # Log more of the bad output
        return None
    except Exception as e:
        logging.error(f"Unexpected error processing scene plan: {e}")
        return None


# --- Main Workflow ---
def main(num_scenes_requested, model_name): # Renamed input param
    """Orchestrates the story generation process with planning and multiple roles."""
    # --- Initial Setup ---
    start_time = time.time()

    # Use the initial base directory name for setup
    current_output_dir = BASE_OUTPUT_DIR
    # Logging is already set up to use initial_log_dir (which is BASE_OUTPUT_DIR)

    try:
        llm_roles = load_roles()
    except Exception as e:
        logging.critical(f"FATAL: Failed to initialize roles from {ROLES_FILE}. Cannot continue. Error: {e}")
        return

    # Ensure base directory exists (logging setup might have already done this)
    if not os.path.exists(current_output_dir):
        try:
            os.makedirs(current_output_dir)
            logging.info(f"Created output directory: {current_output_dir}")
        except OSError as e:
             logging.critical(f"FATAL: Failed to create output directory {current_output_dir}. Cannot continue. Error: {e}")
             return

    # --- STEP 0: Generate Scene Plan ---
    # Pass the current output directory to the planner function
    scene_plans = generate_scene_plan(llm_roles, model_name, num_scenes_requested, current_output_dir)
    if scene_plans is None:
        logging.critical("FATAL: Failed to generate scene plan. Cannot proceed with scene generation.")
        return

    # Use the *actual* number of plans generated for the loop
    num_scenes_to_generate = len(scene_plans)
    logging.info(f"Proceeding to generate {num_scenes_to_generate} scenes based on the plan.")


    # --- Scene Generation Loop ---
    approved_scenes_content = []
    story_context = {
        "summary": STORY_SUMMARY,
        "approved_scene_texts": [],
        "themes": "Heroism, Found Family, Strategy vs Brute Force, Ancient Lore",
        "world_notes": "Medieval fantasy Eldoria, Firepeak Mountains (dangerous), subtle magic influencing minds, political alliances matter."
    }

    # *** Loop uses num_scenes_to_generate ***
    for scene_num in range(1, num_scenes_to_generate + 1):
        logging.info(f"\n{'='*15} Processing Scene {scene_num}/{num_scenes_to_generate} {'='*15}")
        scene_plan_outline = scene_plans[scene_num - 1] # Get the specific plan for this scene
        logging.info(f"Scene Plan Outline: {scene_plan_outline}")

        # Scene-specific state (reset for each scene)
        current_draft = None
        initial_critique = "No critique generated yet."
        synthesized_critique = "No critique generated yet."
        scene_approved = False
        revision_count = 0
        abort_scene = False

        last_approved_scene_text = story_context["approved_scene_texts"][-1] if story_context["approved_scene_texts"] else "This is the beginning of the story."

        while not scene_approved and revision_count < MAX_REVISIONS_PER_SCENE and not abort_scene:
            revision_count += 1
            logging.info(f"\n--- Scene {scene_num}, Revision Cycle {revision_count} ---")

            # --- Step 1: Initial Write / Get Current Draft ---
            if revision_count == 1:
                logging.info("[Writer - Step 1] Generating initial draft...")
                writer_task = (
                    f"Write Scene {scene_num} of the story based on the specific scene plan outline provided below. This is scene {scene_num} out of {num_scenes_to_generate} planned scenes.\n\n" # Clarified scene count context
                    f"**Scene {scene_num} Plan/Goal:** {scene_plan_outline}\n\n" # *** USE THE PLAN ***
                    f"Overall Story Summary:\n{story_context['summary']}\n\n"
                    f"Previous Scene Context:\n{last_approved_scene_text}\n\n"
                    f"World Notes:\n{story_context['world_notes']}\n\n"
                    f"Themes to consider:\n{story_context['themes']}\n\n"
                    f"Instructions: Write a compelling scene that fulfills the Scene Plan/Goal. Ensure actions, dialogue, and descriptions are vivid and consistent. Advance the plot according to the plan."
                )
                draft_1 = call_ollama_role(llm_roles['PrimaryWriter']['system_prompt'], writer_task, model_name)
                if draft_1 is None:
                    logging.error(f"CRITICAL FAILURE: Writer failed initial draft for Scene {scene_num} after retries. Aborting this scene.")
                    abort_scene = True
                    continue
                current_draft = draft_1
                save_intermediate_file(current_draft, scene_num, "draft_1_initial", revision_count, current_output_dir) # Pass dir
            else:
                 logging.info(f"[Loop] Starting cycle {revision_count} with draft from end of previous cycle.")
                 # current_draft already holds the draft from the previous cycle's Step 4


            # --- Steps 2-7 (Critique, Rewrite, Revise, Specialists, Approve) ---

            # Step 2: Get Critique Source (Initial or Synthesized)
            critique_source = ""
            if revision_count == 1:
                logging.info("[Critiquer - Step 2] Generating initial critique...")
                critiquer_task_initial = (
                    f"You are the Critical Editor performing an initial critique of Scene {scene_num} (out of {num_scenes_to_generate}).\n" # Added total scenes context
                    f"Scene Plan/Goal: {scene_plan_outline}\n" # Add plan for context
                    f"Overall Story Summary:\n{story_context['summary']}\n\n"
                    f"Scene Draft (Draft 1):\n{current_draft}\n\n"
                    f"Task: Provide a structured critique focusing on how well the draft achieves the scene plan, plus clarity, plot, character, pacing, description, impact. Identify 1-3 KEY areas for the Rewriter."
                )
                initial_critique = call_ollama_role(llm_roles['CriticalEditor']['system_prompt'], critiquer_task_initial, model_name)
                if initial_critique is None:
                    logging.warning(f"Initial critique failed for Scene {scene_num}. Using placeholder.")
                    initial_critique = "Critique generation failed. General improvement needed, focusing on the scene plan."
                save_intermediate_file(initial_critique, scene_num, "critique_initial", revision_count, current_output_dir) # Pass dir
                critique_source = initial_critique
            else:
                logging.info("[Loop] Using synthesized critique from previous cycle.")
                critique_source = synthesized_critique # Set at end of previous loop

            # Step 3: Rewrite (Rewriter - LLM 3)
            logging.info("[Rewriter - Step 3] Rewriting based on critique...")
            if not critique_source or critique_source == "No critique generated yet.":
                 logging.warning("No valid critique for Rewriter. Attempting general improvement.")
                 rewriter_task = (
                     f"Rewrite Scene {scene_num} (out of {num_scenes_to_generate}) draft to improve quality, clarity, engagement, vividness, and adherence to the scene plan.\n" # Added total scenes context
                     f"Scene Plan/Goal: {scene_plan_outline}\n"
                     f"Story Summary:\n{story_context['summary']}\n\n"
                     f"Draft to Rewrite:\n{current_draft}"
                 )
            else:
                rewriter_task = (
                    f"Rewrite Scene {scene_num} (out of {num_scenes_to_generate}) draft based *specifically* on the critique. Address all points, especially key areas. Ensure it still meets the scene plan.\n" # Added total scenes context
                    f"Scene Plan/Goal: {scene_plan_outline}\n\n"
                    f"Critique:\n{critique_source}\n\n"
                    f"Draft to Rewrite:\n{current_draft}"
                )
            draft_2 = call_ollama_role(llm_roles['FocusedRewriter']['system_prompt'], rewriter_task, model_name)
            if draft_2 is None:
                logging.warning("Rewriter failed. Using previous draft for Writer Revision.")
                draft_2 = current_draft
            save_intermediate_file(draft_2, scene_num, "draft_2_rewritten", revision_count, current_output_dir) # Pass dir

            # Step 4: Writer's Revision (Writer - LLM 1)
            logging.info("[Writer - Step 4] Performing revision pass...")
            writer_revision_task = (
                f"You are the Primary Writer performing a revision pass on Scene {scene_num} (out of {num_scenes_to_generate}).\n" # Added total scenes context
                f"Integrate improvements from the Rewriter's draft (Draft 2) while ensuring alignment with your vision, story flow, style, and the original scene plan. Refer to the critique provided to the rewriter if needed.\n\n"
                f"Scene Plan/Goal: {scene_plan_outline}\n"
                f"Story Summary:\n{story_context['summary']}\n"
                f"Critique Provided to Rewriter:\n{critique_source}\n\n"
                f"Rewritten Draft (Draft 2):\n{draft_2}\n\n"
                f"Output the final revised scene (Draft 3)."
            )
            draft_3 = call_ollama_role(llm_roles['PrimaryWriter']['system_prompt'], writer_revision_task, model_name)
            if draft_3 is None:
                 logging.warning("Writer revision failed. Using Rewriter's draft for Specialists.")
                 draft_3 = draft_2
            current_draft = draft_3
            save_intermediate_file(current_draft, scene_num, "draft_3_revised", revision_count, current_output_dir) # Pass dir

            # Step 5: Specialist Checks
            logging.info("[Specialists - Step 5] Running checks...")
            specialist_reports = {}
            specialist_failed = False
            # Consistency Checker
            consistency_context_str = "\n\n---\n\n".join(story_context["approved_scene_texts"])
            if not consistency_context_str: consistency_context_str = "No previous approved scenes."
            consistency_task = (
                f"Check Scene {scene_num} (out of {num_scenes_to_generate}) draft for consistency.\n\n" # Added total scenes context
                f"Scene Plan/Goal: {scene_plan_outline}\n"
                f"Overall Summary:\n{story_context['summary']}\n"
                f"World Notes:\n{story_context['world_notes']}\n"
                f"Previous Scenes Context:\n{consistency_context_str}\n\n"
                f"Current Draft (Draft 3):\n{current_draft}\n\n"
                f"Task: Report inconsistencies or 'Consistency Check: Passed.'"
            )
            consistency_report = call_ollama_role(llm_roles['ConsistencyChecker']['system_prompt'], consistency_task, model_name)
            if consistency_report is None:
                logging.warning("Consistency Check failed.")
                consistency_report = "Consistency Check Failed (LLM Error)"
                specialist_failed = True
            specialist_reports['Consistency'] = consistency_report
            save_intermediate_file(consistency_report, scene_num, "report_consistency", revision_count, current_output_dir) # Pass dir
            # Dialogue Doctor
            dialogue_task = (
                f"Analyze dialogue in Scene {scene_num} (out of {num_scenes_to_generate}) draft.\n" # Added total scenes context
                f"Draft (Draft 3):\n{current_draft}\n\n"
                f"Task: Provide feedback or 'Dialogue Check: Passed.'"
            )
            dialogue_report = call_ollama_role(llm_roles['DialogueDoctor']['system_prompt'], dialogue_task, model_name)
            if dialogue_report is None:
                logging.warning("Dialogue Check failed.")
                dialogue_report = "Dialogue Check Failed (LLM Error)"
                specialist_failed = True
            specialist_reports['Dialogue'] = dialogue_report
            save_intermediate_file(dialogue_report, scene_num, "report_dialogue", revision_count, current_output_dir) # Pass dir
            # Pacing & Tension Analyst
            pacing_task = (
                f"Analyze pacing/tension in Scene {scene_num} (out of {num_scenes_to_generate}) draft.\n" # Added total scenes context
                f"Draft (Draft 3):\n{current_draft}\n\n"
                f"Task: Provide feedback or 'Pacing/Tension Check: Passed.'"
            )
            pacing_report = call_ollama_role(llm_roles['PacingTensionAnalyst']['system_prompt'], pacing_task, model_name)
            if pacing_report is None:
                logging.warning("Pacing/Tension Check failed.")
                pacing_report = "Pacing/Tension Check Failed (LLM Error)"
                specialist_failed = True
            specialist_reports['PacingTension'] = pacing_report
            save_intermediate_file(pacing_report, scene_num, "report_pacing", revision_count, current_output_dir) # Pass dir

            if specialist_failed:
                logging.warning("One or more specialist checks failed.")

            # Step 6: Final Synthesis & Approval
            logging.info("[Critiquer - Step 6] Synthesizing reports and making final decision...")
            reports_text = ""
            for rtype, report in specialist_reports.items():
                 if report and not report.strip().endswith("Passed.") and not report.strip().endswith("Failed (LLM Error)"):
                     reports_text += f"--- {rtype} Report ---\n{report}\n\n"
            if not reports_text.strip(): reports_text = "No specific issues raised by specialist checks."

            final_critique_task = (
                f"You are the Critical Editor making the final decision for Scene {scene_num} (out of {num_scenes_to_generate}), Revision {revision_count}.\n" # Added total scenes context
                f"Review the latest draft (Draft 3), the scene plan, and specialist reports.\n\n"
                f"Scene Plan/Goal: {scene_plan_outline}\n" # Add plan context
                f"Overall Summary:\n{story_context['summary']}\n\n"
                f"Latest Draft (Draft 3):\n{current_draft}\n\n"
                f"--- Specialist Reports Summary ---\n{reports_text}\n\n"
                f"--- Decision Task ---\n"
                f"Synthesize all info. Does the scene adequately fulfill its plan and meet quality standards? Is it 'Approved' or 'Needs More Work'?\n"
                f"1. If 'Approved': Output ONLY 'Approved'.\n"
                f"2. If 'Needs More Work': Output 'Needs More Work:' followed by concise, synthesized critique (1-3 points) for the next cycle."
            )
            approval_decision = call_ollama_role(llm_roles['CriticalEditor']['system_prompt'], final_critique_task, model_name)
            if approval_decision is None:
                 logging.error(f"CRITICAL FAILURE: Final Critiquer eval failed for Scene {scene_num}, Rev {revision_count}. Assuming 'Needs More Work'.")
                 approval_decision = f"Needs More Work: Final critique generation failed (LLM Error)."

            logging.info(f"[Critiquer] Decision: {approval_decision.splitlines()[0]}")

            # Step 7: Check Approval and Loop/Exit
            if approval_decision.strip().startswith("Approved"):
                logging.info(f"Scene {scene_num} APPROVED on revision {revision_count}!")
                scene_approved = True
                approved_scenes_content.append(current_draft)
                story_context["approved_scene_texts"].append(current_draft)
                # Save final approved scene *within* the current output dir
                final_filename = f"scene_{scene_num}_final_rev_{revision_count}.txt"
                try:
                    with open(os.path.join(current_output_dir, final_filename), "w", encoding="utf-8") as f: f.write(current_draft)
                    logging.info(f"Saved final approved scene: {final_filename}")
                except (IOError, OSError) as e: logging.error(f"Failed to save final scene {final_filename}: {e}")
            else:
                synthesized_critique = approval_decision.replace("Needs More Work:", "").strip()
                if not synthesized_critique:
                    synthesized_critique = "General improvements needed based on editor assessment and scene plan."
                    logging.warning("Critiquer output 'Needs More Work' without specific critique. Using generic message.")
                save_intermediate_file(synthesized_critique, scene_num, "critique_synthesized", revision_count, current_output_dir) # Pass dir
                logging.info(f"Scene {scene_num} Needs More Work. Synthesized Critique: {synthesized_critique}")
                # Loop continues...

        # --- End of revision loop for the scene ---
        if abort_scene:
            logging.error(f"Scene {scene_num} processing ABORTED due to critical failure.")
        elif not scene_approved:
            logging.warning(f"Scene {scene_num} FAILED TO BE APPROVED after {MAX_REVISIONS_PER_SCENE} revisions. Saving last draft as unapproved.")
            # Save unapproved final draft *within* the current output dir
            save_intermediate_file(current_draft, scene_num, "unapproved_final_draft", revision_count, current_output_dir) # Pass dir


    # --- End of all scene generation ---
    end_time = time.time()
    total_time = end_time - start_time
    logging.info("\n" + "="*20 + " Story Generation Finished " + "="*20)
    logging.info(f"Total processing time: {total_time:.2f} seconds ({total_time/60:.2f} minutes).")

    # --- Final Output ---
    final_story_text = f"Story Summary:\n{STORY_SUMMARY}\n\n"
    final_story_text += "=" * 60 + "\n\n"
    if approved_scenes_content:
        final_story_text += f"Generated {len(approved_scenes_content)} Approved Scenes (out of {num_scenes_to_generate} planned):\n\n" # Use actual generated count
        for i, scene_text in enumerate(approved_scenes_content):
            final_story_text += f"--- Scene {i+1} ---\n\n{scene_text}\n\n"
            final_story_text += "=" * 60 + "\n\n"
    else:
        final_story_text += f"No scenes were successfully approved during generation ({num_scenes_to_generate} planned)." # Use actual count

    # Save the final consolidated story text file inside the current output directory
    final_story_filename = "final_story_planned_robust.txt"
    final_story_filepath = os.path.join(current_output_dir, final_story_filename)
    try:
        with open(final_story_filepath, "w", encoding="utf-8") as f:
            f.write(final_story_text)
        logging.info(f"Final story output saved to: {final_story_filepath}")
    except (IOError, OSError) as e:
        logging.error(f"CRITICAL FAILURE: Error saving final story file {final_story_filepath}: {e}")
        # Decide if we should still attempt rename? Probably yes.

    # --- Rename Output Directory ---
    final_output_dir = None
    try:
        # Create a timestamp string
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # Create the new directory name
        final_output_dir = f"{BASE_OUTPUT_DIR}_{timestamp}"

        # Ensure no directory with the final name already exists (highly unlikely, but safe)
        if os.path.exists(final_output_dir):
             final_output_dir = f"{final_output_dir}_1" # Simple collision avoidance

        # Rename the directory
        os.rename(current_output_dir, final_output_dir)
        logging.info(f"Successfully renamed output directory from '{current_output_dir}' to '{final_output_dir}'")
        # Update log file path reference for the final message
        final_log_file = os.path.join(final_output_dir, 'story_generator.log')

    except OSError as e:
        logging.error(f"Failed to rename output directory '{current_output_dir}' to '{final_output_dir}': {e}")
        # Keep the original names if rename fails
        final_output_dir = current_output_dir
        final_log_file = os.path.join(final_output_dir, 'story_generator.log')

    logging.info(f"\nProcess complete. Generated {len(approved_scenes_content)} approved scenes out of {num_scenes_to_generate} planned.")
    logging.info(f"Check the '{final_output_dir}' directory for all generated files and '{final_log_file}' for detailed logs.")


# --- Script Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a story using a planned, multi-LLM workflow (robust).")
    parser.add_argument("scenes", type=int, help="The target number of scenes to plan for.")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Ollama model to use (default: {DEFAULT_MODEL})")

    args = parser.parse_args()

    main(args.scenes, args.model)