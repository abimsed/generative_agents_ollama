import os
import sys
import json
import re

# Set up module path resolution
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from persona.persona import Persona
from persona.prompt_template.gpt_structure import GPT_request

# File paths
STORAGE_BASE = "/Users/abim/Abim/practice/generative_agents_ollama/environment/frontend_server/storage/base_gen_students/personas"
SYLLABUS_FILE = os.path.join(current_dir, "syllabi", "cs201_intro.json")
OUTPUT_LOG_FILE = os.path.join(current_dir, "syllabus_onboarding_audit.json")

PERSONAS_TO_TEST = ["Abi", "Tim"]


def load_json_file(filepath):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found at: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_json_response(raw_text):
    text = raw_text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx : end_idx + 1]

    try:
        return json.loads(text, strict=False)
    except Exception:
        sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
        try:
            return json.loads(sanitized, strict=False)
        except Exception:
            return {
                "internal_monologue": raw_text[:140],
                "perceived_concerns": "Failed to parse structured JSON response.",
                "confidence_to_succeed": "Uncertain",
                "immediate_next_step": "Seek clarification"
            }


def build_student_reading_prompt(persona, section_name, section_content, prior_reactions):
    """
    Constructs an unprimed reading prompt pulling foundational beliefs 
    directly from nodes.json and tracking rolling short-term working memory.
    """
    # 1. Pull cognitive seed statements loaded from nodes.json
    core_beliefs = []
    if hasattr(persona, "a_mem") and hasattr(persona.a_mem, "seq_thought"):
        for node in persona.a_mem.seq_thought:
            core_beliefs.append(f"- {node.description}")
    
    baseline_memories_str = (
        "\n".join(core_beliefs)
        if core_beliefs
        else f"- {persona.scratch.innate}\n- {persona.scratch.learned}"
    )

    # 2. Rolling short-term working memory of earlier sections in this sitting
    context = (
        "\n".join([f"- {r}" for r in prior_reactions[-3:]])
        if prior_reactions
        else "Just opened the syllabus document for the first time."
    )

    prompt = f"""You are simulating student '{persona.name}' who has just enrolled in an introductory computer science course and is reading through the syllabus before the first day of class.

### FOUNDATIONAL COGNITIVE BELIEFS & HABITS (FROM MEMORY):
{baseline_memories_str}

### PREVIOUS THOUGHTS FROM EARLIER SECTIONS OF THIS SYLLABUS:
{context}

### CURRENT SYLLABUS SECTION BEING READ:
[{section_name}]
{json.dumps(section_content, indent=2)}

### INSTRUCTIONS:
Read this section carefully. Express your genuine, unvarnished internal reaction as {persona.name}. 
What goes through your mind? What concerns, doubts, or red flags do you see, if any? How does this rule or requirement make you feel about your chances of succeeding in this course?

Respond strictly in valid JSON:
{{
  "internal_monologue": "Candid first-person stream of thought as you read this section",
  "perceived_concerns": "Any specific rules, policies, or expectations that worry you, feel unfair, or seem confusing",
  "confidence_to_succeed": "High / Moderate / Low / Discouraged",
  "immediate_next_step": "What you plan to do after reading this section"
}}"""
    return prompt


def run_syllabus_onboarding():
    syllabus = load_json_file(SYLLABUS_FILE)

    syllabus_sections = [
        ("Course Overview & Prerequisites", syllabus.get("course_metadata", {})),
        ("Required Toolchain & Software", syllabus.get("toolchain_and_software", {})),
        ("Grading Scheme & Project Weights", syllabus.get("grading_scheme", {})),
        ("Late Submission & Deadlines", {
            "late_policy": syllabus.get("course_policies", {}).get("late_submission_policy"),
            "zero_credit_rules": syllabus.get("course_policies", {}).get("zero_credit_conditions")
        }),
        ("Academic Dishonesty & Collaboration Rules", syllabus.get("academic_integrity", {})),
        ("Attendance & Participation Policy", syllabus.get("course_policies", {}).get("attendance_and_participation", {}))
    ]

    print("=" * 80)
    print("PHASE 1: SYLLABUS ONBOARDING SIMULATION")
    print(f"Course: {syllabus.get('course_metadata', {}).get('course_title')}")
    print("=" * 80)

    # Initialize personas (loads both scratch.json and nodes.json)
    personas = {}
    persona_working_memory = {name: [] for name in PERSONAS_TO_TEST}

    for name in PERSONAS_TO_TEST:
        persona_folder = os.path.join(STORAGE_BASE, name)
        if not os.path.exists(persona_folder):
            print(f"[ERROR] Directory for {name} not found at: {persona_folder}")
            return
        personas[name] = Persona(name, persona_folder)

    audit_records = []

    for idx, (sec_name, sec_data) in enumerate(syllabus_sections, start=1):
        print(f"\n[{idx}/{len(syllabus_sections)}] Reading Section: {sec_name}")
        print("-" * 80)

        section_entry = {"section": sec_name, "evaluations": {}}

        for name in PERSONAS_TO_TEST:
            persona = personas[name]
            prior_mems = persona_working_memory[name]

            # Student reads syllabus section naturally
            read_prompt = build_student_reading_prompt(persona, sec_name, sec_data, prior_mems)
            raw_response = GPT_request(read_prompt)
            student_output = clean_json_response(raw_response)

            # Display raw student output in console
            print(f"  [{name}] Confidence: {student_output.get('confidence_to_succeed')}")
            print(f"  [{name}] Monologue:  {student_output.get('internal_monologue')}")
            print(f"  [{name}] Concerns:   {student_output.get('perceived_concerns')}")
            print(f"  [{name}] Action:     {student_output.get('immediate_next_step')}\n")

            # Update rolling working memory for the ongoing reading session
            memory_entry = (
                f"Read '{sec_name}': Felt {student_output.get('confidence_to_succeed')}. "
                f"Thought: '{student_output.get('internal_monologue')[:80]}'."
            )
            persona_working_memory[name].append(memory_entry)

            section_entry["evaluations"][name] = student_output

        audit_records.append(section_entry)

    # Save outputs to JSON
    with open(OUTPUT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(audit_records, f, indent=2)

    print("=" * 80)
    print(f"SIMULATION COMPLETE. Raw qualitative reactions saved to: {OUTPUT_LOG_FILE}")
    print("=" * 80)


if __name__ == "__main__":
    run_syllabus_onboarding()