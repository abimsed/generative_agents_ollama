import os
import sys
import json
import re
from datetime import datetime

# Adjust path to import generative_agents modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from persona.persona import Persona
from persona.prompt_template.gpt_structure import GPT_request, get_embedding

# Configuration Paths
STORAGE_BASE = "/Users/abim/Abim/practice/generative_agents_ollama/environment/frontend_server/storage/base_gen_students/personas"
CURRICULUM_FILE = os.path.join(current_dir, "curriculum_tasks.json")
SYLLABUS_FILE = os.path.join(current_dir, "syllabi", "cs201_intro.json")
OUTPUT_LOG_FILE = os.path.join(current_dir, "inclusivity_audit_results_cumulative.json")

PERSONAS_TO_TEST = ["Abi", "Tim"]


def load_json_file(filepath):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found at: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_json_response(raw_text):
    """
    Cleans markdown formatting and parses raw model output into a valid dictionary.
    """
    text = raw_text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        extracted = text[start_idx : end_idx + 1]
    else:
        extracted = text

    try:
        return json.loads(extracted, strict=False)
    except Exception:
        sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', extracted)
        try:
            return json.loads(sanitized, strict=False)
        except Exception as err:
            print(f"\n[PARSE ERROR]: {err}\n[RAW OUTPUT]: {raw_text[:200]}...\n")
            return {
                "internal_monologue": f"Generation error: {raw_text[:100]}",
                "perceived_difficulties": "Failed to parse structured response",
                "next_action": "Seek help",
                "decision_rationale": "Model emitted non-JSON output"
            }


def build_evaluation_prompt(persona, task, syllabus, recent_memories):
    """
    Constructs a prompt injecting:
    1. Syllabus constraints and pressure
    2. Persona cognitive identity
    3. Accumulated episodic memories from prior steps/weeks
    4. The current assignment instruction
    """
    policies = syllabus.get("course_policies", {})
    grading = syllabus.get("grading_scheme", {})
    tools = syllabus.get("toolchain_and_software", {})

    memory_context = "\n".join([f"- {m}" for m in recent_memories[-4:]]) if recent_memories else "No prior assignment experiences yet (beginning of semester)."

    prompt = f"""You are simulating the internal cognition and behavior of student '{persona.name}' in an introductory CS course.

### COURSE CONTEXT & INSTITUTIONAL RULES:
- Course: {syllabus.get('course_metadata', {}).get('course_title')} ({tools.get('programming_language', 'Java')})
- Late Submission Rule: {policies.get('late_submission_policy')}
- Project Weight: {grading.get('weights_percentage', {}).get('projects_total')}% of final grade
- Environment & IDE: {tools.get('ide')}, JDK 17/21
- Backup Policy: {tools.get('backup_mandate')}

### STUDENT PROFILE:
- Name: {persona.name}
- Psychological Baseline: {persona.scratch.innate}
- Problem-Solving & Technical Self-Efficacy: {persona.scratch.learned}

### RECENT EXPERIENCES & ACCUMULATED MEMORY (WHAT HAPPENED PREVIOUSLY):
{memory_context}

### CURRENT ASSIGNMENT TASK:
- Week: {task.get('week')}
- Step {task.get('step_number')}: {task.get('title')}
- Instruction: "{task.get('instruction')}"
- Stated Ambiguity Level: {task.get('ambiguity_score')}/5
- Target Cognitive Facet: {task.get('primary_cognitive_facet')}

### TASK FOR SIMULATION:
Decide how {persona.name} responds right now, conditioned by their accumulated memories and the strict course policies.
You must respond with ONLY a valid JSON object matching this schema:
{{
  "internal_monologue": "First-person candid thoughts, emotional reaction, and self-efficacy reflection",
  "perceived_difficulties": "Specific obstacles or ambiguities identified",
  "next_action": "Direct immediate action (e.g., 'Execute command', 'Carefully read documentation', 'Seek help on forum', 'Stall / Avoid')",
  "decision_rationale": "Why this action was chosen given the student's past track record and course policies"
}}"""
    return prompt


def run_batch_simulation():
    curriculum = load_json_file(CURRICULUM_FILE)
    syllabus = load_json_file(SYLLABUS_FILE)
    
    audit_results = []

    print("=" * 80)
    print("STARTING CUMULATIVE MEMORY SIMULATION (WEEKS 1 - 3)")
    print(f"Syllabus: {syllabus.get('course_metadata', {}).get('course_title')}")
    print("=" * 80)

    # Initialize Personas and memory buffers
    personas = {}
    persona_memories = {name: [] for name in PERSONAS_TO_TEST}

    for name in PERSONAS_TO_TEST:
        persona_folder = os.path.join(STORAGE_BASE, name)
        if not os.path.exists(persona_folder):
            print(f"[ERROR] Directory for {name} not found at: {persona_folder}")
            return
        # personas[name] = Persona(persona_folder)
        personas[name] = Persona(name, persona_folder)

    # Flatten curriculum steps sequentially
    all_steps = []
    for week_obj in curriculum:
        week_num = week_obj.get("week")
        for task in week_obj.get("tasks", []):
            task_copy = dict(task)
            task_copy["week"] = week_num
            task_copy["assignment_title"] = week_obj.get("assignment_title")
            all_steps.append(task_copy)

    # Step through curriculum
    for idx, step in enumerate(all_steps, start=1):
        print(f"\n[{idx}/{len(all_steps)}] Week {step['week']} Step {step['step_number']}: {step['title']}")
        print(f"Instruction: \"{step['instruction']}\"")
        print(f"Target Facet: {step['primary_cognitive_facet']} | Ambiguity: {step['ambiguity_score']}/5")
        print("-" * 80)

        step_audit = {
            "step_index": idx,
            "week": step["week"],
            "step_number": step["step_number"],
            "title": step["title"],
            "instruction": step["instruction"],
            "ambiguity_score": step["ambiguity_score"],
            "target_facet": step["primary_cognitive_facet"],
            "evaluations": {}
        }

        for name in PERSONAS_TO_TEST:
            persona = personas[name]
            recent_mems = persona_memories[name]

            prompt = build_evaluation_prompt(persona, step, syllabus, recent_mems)
            raw_response = GPT_request(prompt)
            parsed = clean_json_response(raw_response)

            print(f"  [{name}] Next Action: {parsed.get('next_action', 'N/A')}")
            print(f"  [{name}] Monologue:   {parsed.get('internal_monologue', 'N/A')}")
            print(f"  [{name}] Blocker:     {parsed.get('perceived_difficulties', 'N/A')}\n")

            # Formulate episodic memory node
            action = parsed.get("next_action", "Attempted task")
            monologue = parsed.get("internal_monologue", "")
            difficulties = parsed.get("perceived_difficulties", "")

            memory_sentence = (
                f"In Week {step['week']} ({step['title']}), I encountered: '{difficulties[:80]}'. "
                f"I felt: '{monologue[:80]}'. My action was: '{action}'."
            )
            
            persona_memories[name].append(memory_sentence)

            # Insert into runtime associative memory stream (a_mem)
            if hasattr(persona, "a_mem"):
                try:
                    emb = get_embedding(memory_sentence)
                    persona.a_mem.add_thought(
                        created=datetime.now(),
                        expiration=None,
                        s=persona.name,
                        p="experienced",
                        o=step['title'],
                        description=memory_sentence,
                        embedding_pair=(memory_sentence, emb),
                        poignancy=6
                    )
                except Exception:
                    pass

            step_audit["evaluations"][name] = parsed

        audit_results.append(step_audit)

    with open(OUTPUT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, indent=2)

    print("\n" + "=" * 80)
    print(f"SIMULATION COMPLETE. Cumulative audit log saved to: {OUTPUT_LOG_FILE}")
    print("=" * 80)


if __name__ == "__main__":
    run_batch_simulation()