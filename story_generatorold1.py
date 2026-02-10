import requests
import json
import os
import argparse
import logging
import time

# --- Configuration ---
OLLAMA_API_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "gemma3:27b" # Or choose another powerful model you have
ROLES_FILE = "llm_roles.json"
MAX_REVISIONS_PER_SCENE = 20 # Safety break to prevent infinite loops
OUTPUT_DIR = "story_output" # Directory to save scenes

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Role Loading ---
def load_roles(filepath=ROLES_FILE):
    """Loads the LLM role prompts from a JSON file."""
    if not os.path.exists(filepath):
        logging.error(f"Role configuration file not found: {filepath}")
        raise FileNotFoundError(f"Role configuration file not found: {filepath}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            roles = json.load(f)
        logging.info(f"Successfully loaded {len(roles)} roles from {filepath}")
        return roles
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {filepath}: {e}")
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading {filepath}: {e}")
        raise

# --- Ollama API Interaction ---
def call_ollama_role(system_prompt, user_message, model_name, context_messages=None, temperature=0.7, top_p=0.9, format_json=False):
    """Sends a request to the Ollama API with a specific role and task."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if context_messages: # Add previous conversation turns if needed
         messages.extend(context_messages)
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": top_p
            # Add other options like num_predict if desired
        }
    }
    if format_json:
         payload["format"] = "json" # Use only if the prompt explicitly guarantees JSON output

    logging.debug(f"Sending payload to Ollama ({model_name}): {json.dumps(payload, indent=2)}")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(OLLAMA_API_URL, json=payload, timeout=180) # Increased timeout
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            response_data = response.json()
            message_content = response_data.get('message', {}).get('content', '')

            if not message_content:
                 logging.warning(f"Ollama returned an empty message for model {model_name}. Payload: {payload}")
                 # Handle empty response, maybe retry or return None/empty string
                 return "" # Or None, depending on how you want to handle failures

            logging.debug(f"Received response from Ollama ({model_name}): {message_content[:200]}...") # Log beginning of response
            return message_content.strip()

        except requests.exceptions.Timeout:
            logging.warning(f"Ollama request timed out (attempt {attempt + 1}/{max_retries}). Retrying...")
            time.sleep(5 * (attempt + 1)) # Exponential backoff
        except requests.exceptions.RequestException as e:
            logging.error(f"Ollama API request failed (attempt {attempt + 1}/{max_retries}): {e}")
            logging.error(f"Failed Payload: {json.dumps(payload, indent=2)}")
            if 'response' in locals() and response is not None:
                logging.error(f"Response status: {response.status_code}, Response text: {response.text}")
            time.sleep(5 * (attempt + 1))
        except json.JSONDecodeError as e:
             logging.error(f"Failed to decode Ollama JSON response (attempt {attempt + 1}/{max_retries}): {e}")
             logging.error(f"Raw Response Text: {response.text if 'response' in locals() else 'N/A'}")
             time.sleep(5 * (attempt + 1)) # Wait before retrying if response was bad

    logging.error(f"Ollama API call failed after {max_retries} retries.")
    return None # Indicate failure after retries

# --- Main Workflow ---
def main(story_summary, num_scenes, model_name):
    """Orchestrates the story generation process."""
    try:
        llm_roles = load_roles()
    except Exception as e:
        logging.error(f"Failed to initialize roles: {e}")
        return

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        logging.info(f"Created output directory: {OUTPUT_DIR}")

    approved_scenes = []
    story_context = { # Simple context for now
        "summary": story_summary,
        "approved_scene_texts": [], # Store text of approved scenes
        "themes": "Heroism, Rescue, Fantasy Conflict", # Example themes
        "world_notes": "Medieval fantasy setting, dragons exist, princesses need saving." # Example world notes
    }

    for scene_num in range(1, num_scenes + 1):
        logging.info(f"\n{'='*10} Generating Scene {scene_num}/{num_scenes} {'='*10}")
        current_draft = None
        critique = ""
        revision_count = 0
        scene_approved = False
        last_approved_scene_text = story_context["approved_scene_texts"][-1] if story_context["approved_scene_texts"] else "This is the first scene."

        while not scene_approved and revision_count < MAX_REVISIONS_PER_SCENE:
            revision_count += 1
            logging.info(f"\n--- Scene {scene_num}, Revision Cycle {revision_count} ---")

            # === Step 1: Write/Revise Scene (LLM 1 - PrimaryWriter) ===
            logging.info("[Writer] Generating draft...")
            writer_task = ""
            if current_draft is None: # First draft attempt for this scene
                writer_task = (
                    f"Write Scene {scene_num} of a story.\n"
                    f"Overall Story Summary: {story_context['summary']}\n"
                    f"Previous Scene Summary/Ending: {last_approved_scene_text}\n"
                    f"Focus on moving the plot towards the goal based on the summary."
                )
            else: # Revising based on previous critique
                 writer_task = (
                    f"You are revising Scene {scene_num}. Below is the latest draft and the critique from the Critical Editor. \n"
                    f"Your task is to perform a final revision based on this critique, integrating the required improvements while ensuring the scene aligns with your original creative vision and the overall story flow ({story_context['summary']}).\n\n"
                    f"Critique:\n{critique}\n\n"
                    f"Latest Draft to Revise:\n{current_draft}"
                 )
                 # Note: This deviates slightly from the 6-step flow by having the Writer do the revision based *directly* on the Critiquer's feedback if rejected.
                 # The original flow had Rewriter -> Writer(revise) -> Critiquer(approve). This simplifies the loop if rejection happens.

            current_draft = call_ollama_role(
                llm_roles['PrimaryWriter']['system_prompt'],
                writer_task,
                model_name
            )
            if current_draft is None:
                logging.error("Writer failed to generate content. Skipping scene.")
                break # Exit revision loop for this scene
            logging.debug(f"[Writer] Draft {revision_count}:\n{current_draft[:300]}...")
            # Save intermediate draft (optional)
            with open(os.path.join(OUTPUT_DIR, f"scene_{scene_num}_draft_{revision_count}.txt"), "w", encoding="utf-8") as f:
                f.write(current_draft)


            # === Step 2 & 6 Combined: Critique & Approval Check (LLM 2 - CriticalEditor) ===
            # We'll use the Critiquer to both provide feedback AND make the approval decision in one go after the Writer's pass.
            logging.info("[Critiquer] Evaluating draft...")
            critiquer_task = (
                f"You are the Critical Editor. Evaluate the following draft for Scene {scene_num}. The overall story summary is: {story_context['summary']}.\n\n"
                # Add specialist context here if they were run
                # f"Consistency Check Report: {consistency_report}\n"
                # f"Dialogue Check Report: {dialogue_report}\n"
                # ... etc ...
                f"Scene Draft:\n{current_draft}\n\n"
                f"Based on this draft and any specialist reports (if provided), is this scene 'Approved' or does it 'Needs More Work'? "
                f"If 'Approved', just say 'Approved'. "
                f"If 'Needs More Work', state 'Needs More Work:' followed by a concise, actionable critique (1-3 bullet points) focusing on the *most important* changes needed for the next revision by the Primary Writer."
            )

            approval_decision = call_ollama_role(
                llm_roles['CriticalEditor']['system_prompt'],
                critiquer_task,
                model_name
            )
            if approval_decision is None:
                 logging.error("Critiquer failed to generate evaluation. Assuming Needs More Work.")
                 approval_decision = "Needs More Work: Critiquer LLM failed to respond."

            logging.info(f"[Critiquer] Decision: {approval_decision}")


            # === Step 7: Check Approval and Loop ---
            if approval_decision.strip().startswith("Approved"):
                logging.info(f"Scene {scene_num} Approved!")
                scene_approved = True
                approved_scenes.append(current_draft)
                story_context["approved_scene_texts"].append(current_draft) # Add to our simple context
                # Save final approved scene
                with open(os.path.join(OUTPUT_DIR, f"scene_{scene_num}_final.txt"), "w", encoding="utf-8") as f:
                    f.write(current_draft)
            else:
                critique = approval_decision.replace("Needs More Work:", "").strip()
                logging.info(f"Scene {scene_num} Needs More Work. Critique: {critique}")
                # The loop will continue, feeding this critique back to the Writer (Step 1)

        # End of revision loop for the scene
        if not scene_approved:
            logging.warning(f"Scene {scene_num} could not be approved after {MAX_REVISIONS_PER_SCENE} revisions. Moving on.")
            # Optionally save the last draft anyway
            if current_draft:
                 with open(os.path.join(OUTPUT_DIR, f"scene_{scene_num}_unapproved_final.txt"), "w", encoding="utf-8") as f:
                     f.write(current_draft)

    # End of scene generation loop
    logging.info("\n" + "="*20 + " Story Generation Complete " + "="*20)

    # --- Final Output ---
    final_story_text = f"Story Summary: {story_summary}\n\n"
    final_story_text += "=" * 40 + "\n\n"
    for i, scene_text in enumerate(approved_scenes):
        final_story_text += f"--- Scene {i+1} ---\n\n{scene_text}\n\n"
        final_story_text += "=" * 40 + "\n\n"

    output_filename = os.path.join(OUTPUT_DIR, "final_story.txt")
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(final_story_text)
        logging.info(f"Final story saved to: {output_filename}")
    except Exception as e:
        logging.error(f"Error saving final story: {e}")

    logging.info(f"Generated {len(approved_scenes)} approved scenes out of {num_scenes} requested.")


# --- Script Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a story using a multi-LLM workflow with Ollama.")
    parser.add_argument("summary", help="A brief summary of the desired story.")
    parser.add_argument("scenes", type=int, help="The target number of scenes.")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Ollama model to use (default: {DEFAULT_MODEL})")
    # Add arguments for temperature, top_p etc. if needed

    args = parser.parse_args()

    main(args.summary, args.scenes, args.model)
# python3 story_generator.py "A brave knight must journey through an enchanted forest to find a hidden cave where a fearsome dragon holds a princess captive. He needs to defeat the dragon and rescue the princess." 3