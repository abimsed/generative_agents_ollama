import os
import sys
import json
import re

# Ensure local backend imports resolve cleanly
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from persona.persona import Persona
from persona.prompt_template.gpt_structure import GPT_request


# Configuration & Paths
# STORAGE_BASE = "../frontend_server/storage/base_gen_students/personas"
STORAGE_BASE = "/Users/abim/Abim/practice/generative_agents_ollama/environment/frontend_server/storage/base_gen_students/personas"
CURRICULUM_TASKS_FILE = "curriculum_tasks.json"
OUTPUT_REPORT_FILE = "simulation_inclusivity_audit.json"
TARGET_PERSONAS = ["Abi", "Tim"]


# def clean_json_response(raw_text):
#     """
#     Strips markdown code fences and isolates valid JSON strings.
#     """
#     text = raw_text.strip()
#     text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
#     text = re.sub(r"^```\s*", "", text)
#     text = re.sub(r"\s*```$", "", text)
    
#     start_idx = text.find("{")
#     end_idx = text.rfind("}")
    
#     if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
#         text = text[start_idx : end_idx + 1]
    
#     try:
#         return json.loads(text)
#     except Exception:
#         return {
#             "error": "Failed to parse JSON response from local model",
#             "raw_output": raw_text
#         }

def clean_json_response(raw_text):
    """
    Strips markdown code fences and isolates valid JSON strings.
    """
    text = raw_text.strip()
    # Remove markdown code blocks if wrapped
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        extracted = text[start_idx : end_idx + 1]
    else:
        extracted = text

    # Attempt 1: Direct parse
    try:
        return json.loads(extracted, strict=False)
    except Exception:
        pass

    # Attempt 2: Clean stray control characters/newlines
    try:
        sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', extracted)
        return json.loads(sanitized, strict=False)
    except Exception as err:
        print(f"\n[PARSE ERROR]: {err}")
        print(f"[RAW OUTPUT WAS]:\n{raw_text}\n")
        return {
            "internal_monologue": f"[Generation Error] Raw output: {raw_text[:120]}...",
            "perceived_difficulties": "Parsing error encountered",
            "next_action": "Seek help (Script Parse Fallback)",
            "decision_rationale": "Model emitted non-compliant JSON string."
        }
    
def load_week_by_week_tasks(filepath):
    """
    Loads curriculum tasks nested by week and flattens them for iterative evaluation
    while retaining module and weekly metadata.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Curriculum tasks file not found: {filepath}")
    
    with open(filepath, "r", encoding="utf-8") as f:
        weeks_data = json.load(f)

    flat_task_list = []
    for week_block in weeks_data:
        week_num = week_block.get("week")
        topic = week_block.get("module_topic")
        assignment = week_block.get("assignment_title")
        
        for task in week_block.get("tasks", []):
            task["week"] = week_num
            task["module_topic"] = topic
            task["assignment_title"] = assignment
            flat_task_list.append(task)

    return flat_task_list


def build_evaluation_prompt(persona, task):
    """
    Constructs the cognitive evaluation prompt combining the agent's
    profile with the specific task instruction.
    """
    persona_name = persona.name
    
    innate_traits = getattr(persona.scratch, "innate", "Not specified")
    learned_traits = getattr(persona.scratch, "learned", "Not specified")
    lifestyle = getattr(persona.scratch, "lifestyle", "Not specified")
    
    reflections = []
    if hasattr(persona, "a_mem") and hasattr(persona.a_mem, "seq_thought"):
        for thought in persona.a_mem.seq_thought[-5:]:
            if hasattr(thought, "description"):
                reflections.append(f"- {thought.description}")
    
    reflection_str = "\n".join(reflections) if reflections else "No prior recorded reflections."

    prompt = f"""You are simulating the authentic thought process and behavior of a student named {persona_name} in an introductory Computer Science course.

### STUDENT COGNITIVE PROFILE:
- Name: {persona_name}
- Innate Characteristics: {innate_traits}
- Learned Background & Problem-Solving Style: {learned_traits}
- Lifestyle & Mindset: {lifestyle}

### RECENT EXPERIENCES / REFLECTIONS:
{reflection_str}

### CURRENT TASK ASSIGNED BY INSTRUCTOR:
Week: {task.get('week')} ({task.get('module_topic')})
Assignment: {task.get('assignment_title')}
Step {task.get('step_number')}: {task.get('title')}
Instruction:
\"\"\"{task.get('instruction')}\"\"\"

### EVALUATION DIRECTIVE:
Simulate how {persona_name} reacts to this specific step. Ground your response in their risk tolerance, computer self-efficacy, and problem-solving style (tinkering vs. process-oriented).
Do NOT break character.

Respond strictly in valid JSON with these EXACT keys:
{{
  "internal_monologue": "First-person thoughts and immediate feelings upon reading this instruction.",
  "perceived_difficulties": "Specific phrasing or technical demands that feel risky, confusing, intimidating, or exciting.",
  "next_action": "The single immediate action you take next (e.g., 'Execute command', 'Poke around settings', 'Search documentation', 'Ask TA/instructor for help', 'Abandon task').",
  "decision_rationale": "Why you chose this action based on your self-efficacy and risk-aversion."
}}
"""
    return prompt


def run_batch_simulation():
    print("=" * 80)
    print("STARTING SIMULATION (OLLAMA)")
    print("=" * 80)

    tasks = load_week_by_week_tasks(CURRICULUM_TASKS_FILE)
    print(f"Loaded {len(tasks)} curriculum steps from the schedule.\n")

    # Load personas into memory
    persona_instances = {}
    for p_name in TARGET_PERSONAS:
        p_folder = os.path.join(STORAGE_BASE, p_name)
        if not os.path.exists(p_folder):
            print(f"[ERROR] Directory for {p_name} not found at: {p_folder}")
            continue
        print(f"Loading persona state: {p_name}...")
        persona_instances[p_name] = Persona(p_name, p_folder)

    if not persona_instances:
        print("[FATAL] No personas loaded. Exiting.")
        return

    audit_records = []
    current_week = None

    for idx, task in enumerate(tasks, 1):
        if task.get("week") != current_week:
            current_week = task.get("week")
            print("\n" + "=" * 80)
            print(f"WEEK {current_week}: {task.get('module_topic').upper()} - {task.get('assignment_title')}")
            print("=" * 80)

        print(f"\n[{idx}/{len(tasks)}] Step {task.get('step_number')}: {task.get('title')}")
        print(f"Instruction: \"{task.get('instruction')}\"")
        print(f"Target Facet: {task.get('primary_cognitive_facet')} | Ambiguity: {task.get('ambiguity_score')}/5")
        print("-" * 80)

        step_record = {
            "task_id": task.get("task_id"),
            "week": task.get("week"),
            "module_topic": task.get("module_topic"),
            "assignment_title": task.get("assignment_title"),
            "step_number": task.get("step_number"),
            "instruction": task.get("instruction"),
            "scaffolding_level": task.get("scaffolding_level"),
            "ambiguity_score": task.get("ambiguity_score"),
            "primary_cognitive_facet": task.get("primary_cognitive_facet"),
            "expected_friction": task.get("expected_friction"),
            "evaluations": {}
        }

        for p_name, persona in persona_instances.items():
            prompt = build_evaluation_prompt(persona, task)
            raw_response = GPT_request(prompt)
            parsed_output = clean_json_response(raw_response)

            step_record["evaluations"][p_name] = parsed_output

            # Terminal printout
            action = parsed_output.get("next_action", "N/A")
            print(f"  [{p_name}] Next Action: {action}")
            print(f"  [{p_name}] Monologue:   {parsed_output.get('internal_monologue', 'N/A')}")
            print(f"  [{p_name}] Blocker:     {parsed_output.get('perceived_difficulties', 'N/A')}\n")

        audit_records.append(step_record)

    # Write complete simulation results to JSON
    with open(OUTPUT_REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(audit_records, f, indent=2)

    print("=" * 80)
    print(f"SIMULATION RUN FINISHED. Audit log saved to: {OUTPUT_REPORT_FILE}")
    print("=" * 80)


if __name__ == "__main__":
    run_batch_simulation()

# import os
# import json
# from datetime import datetime
# from persona.persona import Persona
# from persona.prompt_template.gpt_structure import GPT_request, get_embedding

# TEST_LAB_0_PROMPT = """
# Welcome to CS 101: Lab 0 Environment Setup.
# Objective: Get your development environment ready for the semester.

# Instructions:
# 1. Clone the project repository from GitHub.
# 2. Install the necessary Python packages and build dependencies. 
# 3. Open 'config.env' and tweak the system environment variables until the local server starts cleanly.
# 4. If you get a cryptic exit code 127 error, just poke around the config and experiment with different path configurations until it connects.
# 5. Once running, submit a screenshot of your terminal to the portal.
# """

# def evaluate_persona_interaction(persona_name, persona_folder, curriculum_text):
#     print(f"\n{'='*70}\nRunning Simulation for: {persona_name}\n{'='*70}")
    
#     persona = Persona(persona_name, persona_folder)
    
#     # 1. Generate event embedding and register with matching s, p, o parameter names
#     event_desc = f"{persona_name} is reading the CS101 Lab 0 assignment: {curriculum_text.strip()}"
#     emb_vec = get_embedding(event_desc)
    
#     persona.a_mem.add_event(
#         created=datetime.now(),
#         expiration=None,
#         s=persona_name,
#         p="reads",
#         o="CS101 Lab 0 instructions",
#         description=event_desc,
#         keywords=["curriculum", "CS101", "Lab 0", "setup", "instructions"],
#         poignancy=5,
#         embedding_pair=(event_desc, emb_vec),
#         filling=[]
#     )
    
#     # 2. Retrieve background thoughts directly from the memory stream sequence
#     retrieved_thoughts = [node.description for node in persona.a_mem.seq_thought]
#     retrieved_context = "\n".join([f"- {desc}" for desc in retrieved_thoughts])
    
#     # 3. Formulate prompt without priming for bugs
#     reaction_prompt = f"""You are {persona.scratch.name}.
# Background & Work Style:
# {persona.scratch.learned}

# Relevant Thoughts & Past Experiences:
# {retrieved_context}

# You have just received the following assignment instructions:
# \"\"\"{curriculum_text}\"\"\"

# Based strictly on your personality, background, and information processing style:
# 1. What is your immediate reaction and internal monologue upon reading this?
# 2. What specific difficulty, concern, or confusion (if any) arises for you?
# 3. What is your concrete next action or decision? Do you proceed, hesitate, seek help, abandon, or experiment?

# Format your response strictly as a valid JSON object with the following keys:
# {{
#   "internal_monologue": "string",
#   "perceived_difficulties": "string",
#   "next_action": "string",
#   "decision_rationale": "string"
# }}
# JSON:"""

#     # 4. Call GPT_request with single argument
#     try:
#         response_str = GPT_request(reaction_prompt)
#     except Exception:
#         import openai
#         res = openai.Completion.create(
#             engine="gpt-3.5-turbo-instruct",
#             prompt=reaction_prompt,
#             max_tokens=500,
#             temperature=0.2
#         )
#         response_str = res.choices[0].text

#     return response_str


# if __name__ == "__main__":
#     storage_base = "../../environment/frontend_server/storage/base_gen_students/personas"
    
#     agents = ["Abi", "Tim"]
#     results = {}

#     for agent in agents:
#         agent_dir = os.path.join(storage_base, agent)
#         if os.path.exists(agent_dir):
#             raw_output = evaluate_persona_interaction(agent, agent_dir, TEST_LAB_0_PROMPT)
#             results[agent] = raw_output
#             print(f"\n--- Output for {agent} ---")
#             print(raw_output)
#         else:
#             print(f"Directory not found for {agent}: {agent_dir}")

#     output_log = "inclusivity_eval_results.json"
#     with open(output_log, "w") as f:
#         json.dump(results, f, indent=2)
#     print(f"\nSaved evaluation responses to {output_log}")