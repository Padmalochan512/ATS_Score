import os
import re
import json 
import logging
from typing import Dict, List

logger = logging.getLogger('ats_resume_scorer')

GROQ_MODEL = 'llama-3.3-70b-versatile'
_client = None

def _get_client():
    global _client
    api_key = os.getenv('GROQ_API_KEY', '').strip()
    if not api_key or api_key.startswith('your_') or api_key == 'placeholder':
        return None
    if _client is None:
        try:
            from groq import Groq
            _client = Groq(api_key=api_key)
        except Exception as e:
            logger.warning(f"Failed to initialize Groq client: {e}")
            return None
    return _client

RESUME_SYSTEM_PROMPT = (
    "You are a resume parser. Extract information from the resume "
    "and return ONLY a valid JSON object. No explanation, no markdown."
)

RESUME_USER_PROMPT = """Extract the following from this resume and return as JSON:
{{
  "name": "full name",
  "email": "email address",
  "phone": "phone number",
  "linkedin": "LinkedIn URL if present, otherwise null",
  "github": "GitHub URL if present, otherwise null",
  "professional_summary": "the full text of the Summary, Profile, About Me, Objective, or Professional Summary section at the top of the resume. Copy the ENTIRE paragraph exactly as written. If no such section exists, return an empty string.",
  "skills": ["list", "of", "skills"],
  "experience": [
    {{
      "job_title": "",
      "company": "",
      "start_date": "",
      "end_date": "",
      "duration_months": 0,
      "description": ""
    }}
  ],
  "education": [
    {{
      "degree": "",
      "institution": "",
      "year": ""
    }}
  ],
  "certifications": ["list of certifications"],
  "projects": [
    {{
      "title": "project name",
      "description": "what the project does and how it was built",
      "technologies": ["tech", "used"]
    }}
  ],
  "action_verbs": ["strong action verbs used in bullet points, e.g. developed, implemented, designed"],
  "keywords": ["important keywords and phrases from the resume for ATS matching"]
}}

Important instructions:
- For duration_months, calculate the number of months between start_date and end_date. If end_date is "Present" or "Current", calculate from start_date to now.
- For skills, extract ALL technical and soft skills mentioned anywhere in the resume.
- For action_verbs, find verbs that start bullet points or describe achievements.
- For keywords, extract noun phrases and technical terms relevant to ATS matching.
- Return ONLY valid JSON. No markdown code fences, no explanation.

Resume Text:
{raw_text}"""

def _call_groq(client, system_prompt: str, user_prompt: str) -> str:
    response = client.chat.completions.create(
        model=GROQ_MODEL, 
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ],
        temperature=0.0,
        max_tokens=4096
    )
    return response.choices[0].message.content.strip()

def _try_parse_json(text: str) -> dict | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_newline + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None

COMMON_SKILLS = [
    "Python", "Java", "C++", "C#", "JavaScript", "TypeScript", "HTML", "CSS", "SQL",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "React", "Next.js", "Angular", "Vue.js",
    "Node.js", "Express", "Django", "FastAPI", "Flask", "Spring Boot", "Docker",
    "Kubernetes", "AWS", "Azure", "GCP", "Git", "GitHub", "CI/CD", "Linux", "REST API",
    "GraphQL", "Machine Learning", "Deep Learning", "Data Science", "NLP", "Pandas",
    "NumPy", "Scikit-Learn", "TensorFlow", "PyTorch", "Tailwind CSS", "Bootstrap",
    "Agile", "Scrum", "Jira", "Figma", "Microservices", "System Design", "Unit Testing",
    "Communication", "Leadership", "Problem Solving", "Teamwork", "Project Management"
]

COMMON_ACTION_VERBS = [
    "developed", "designed", "implemented", "built", "created", "led", "managed",
    "optimized", "engineered", "integrated", "automated", "maintained", "analyzed",
    "spearheaded", "executed", "deployed", "orchestrated", "architected", "delivered",
    "reduced", "increased", "improved", "collaborated", "streamlined", "enhanced"
]

def _fallback_parse_resume(raw_text: str) -> Dict:
    """Local rule-based extractor if Groq API is unavailable."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    
    # Extract Contact Info
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', raw_text)
    email = email_match.group(0) if email_match else None

    phone_match = re.search(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', raw_text)
    phone = phone_match.group(0) if phone_match else None

    linkedin_match = re.search(r'(https?://(?:www\.)?linkedin\.com/in/[\w\-]+)', raw_text, re.IGNORECASE)
    linkedin = linkedin_match.group(0) if linkedin_match else None

    github_match = re.search(r'(https?://(?:www\.)?github\.com/[\w\-]+)', raw_text, re.IGNORECASE)
    github = github_match.group(0) if github_match else None

    name = lines[0] if lines else "Candidate"
    if len(name.split()) > 4:
        name = "Candidate"

    # Extract Skills
    text_lower = raw_text.lower()
    found_skills = [
        skill for skill in COMMON_SKILLS
        if re.search(r'\b' + re.escape(skill.lower()) + r'\b', text_lower)
    ]

    # Extract Action Verbs
    found_verbs = [
        verb for verb in COMMON_ACTION_VERBS
        if re.search(r'\b' + re.escape(verb) + r'\b', text_lower)
    ]

    # Extract Summary
    summary = ""
    summary_match = re.search(
        r'(?:summary|profile|about me|objective)[:\s*\n]+(.*?)(?=\n\s*(?:skills|experience|work|education|projects)|\Z)',
        raw_text,
        re.IGNORECASE | re.DOTALL
    )
    if summary_match:
        summary = summary_match.group(1).strip()[:500]

    # Heuristic projects
    projects = []
    proj_section = re.search(
        r'(?:projects|personal projects)[:\s*\n]+(.*?)(?=\n\s*(?:skills|experience|work|education|certifications)|\Z)',
        raw_text,
        re.IGNORECASE | re.DOTALL
    )
    if proj_section:
        proj_lines = [p.strip() for p in proj_section.group(1).split('\n\n') if p.strip()]
        for p in proj_lines[:5]:
            p_title = p.splitlines()[0]
            projects.append({
                "title": p_title[:80],
                "description": p[:200],
                "technologies": [s for s in found_skills if s.lower() in p.lower()]
            })

    # Heuristic experience
    experience = []
    exp_section = re.search(
        r'(?:experience|work experience|employment)[:\s*\n]+(.*?)(?=\n\s*(?:skills|education|projects|certifications)|\Z)',
        raw_text,
        re.IGNORECASE | re.DOTALL
    )
    if exp_section:
        exp_lines = [e.strip() for e in exp_section.group(1).split('\n\n') if e.strip()]
        for e in exp_lines[:5]:
            e_title = e.splitlines()[0]
            experience.append({
                "job_title": e_title[:80],
                "company": "",
                "start_date": "",
                "end_date": "",
                "duration_months": 12,
                "description": e[:300]
            })

    keywords = list(set(found_skills + found_verbs))

    result = {
        "name": name,
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
        "github": github,
        "professional_summary": summary,
        "skills": found_skills,
        "experience": experience,
        "education": [],
        "certifications": [],
        "projects": projects,
        "action_verbs": found_verbs,
        "keywords": keywords,
    }
    return _validate_resume_result(result)


def parse_resume(raw_text: str) -> Dict:
    client = _get_client()
    if not client:
        logger.info("Using local fallback resume parser (Groq API key not provided or invalid).")
        return _fallback_parse_resume(raw_text)

    try:
        prompt = RESUME_USER_PROMPT.format(raw_text=raw_text)
        raw_response = _call_groq(client, RESUME_SYSTEM_PROMPT, prompt)
        result = _try_parse_json(raw_response)

        if result is not None:
            return _validate_resume_result(result)

        logger.warning("Groq resume parse: first attempt returned invalid JSON, retrying...")
        strict_prompt = (
            "Your previous response was not valid JSON. "
            "Return ONLY the raw JSON object, no markdown, no explanation, no code fences.\n\n"
            + prompt
        )
        raw_response = _call_groq(client, RESUME_SYSTEM_PROMPT, strict_prompt)
        result = _try_parse_json(raw_response)
        if result is not None:
            return _validate_resume_result(result)
    except Exception as exc:
        logger.warning(f"Groq parse_resume failed ({exc}). Falling back to local parser.")
        return _fallback_parse_resume(raw_text)

    return _fallback_parse_resume(raw_text)


JD_SYSTEM_PROMPT = (
    "You are a job description parser. Extract information and "
    "return ONLY a valid JSON object. No explanation, no markdown."
)

JD_USER_PROMPT = """Extract the following from this job description and return as JSON:
{{
  "job_title": "",
  "required_skills": ["list of must-have skills"],
  "preferred_skills": ["list of nice-to-have skills"],
  "experience_required": "",
  "education_required": "",
  "key_responsibilities": ["list of responsibilities"],
  "keywords": ["important keywords and phrases for ATS matching"]
}}

Important instructions:
- required_skills: skills explicitly stated as required or must-have.
- preferred_skills: skills stated as preferred, nice-to-have, or bonus.
- keywords: extract ALL important terms an ATS system would match against,
  including skills, technologies, certifications, and domain terms.
- Return ONLY valid JSON. No markdown code fences, no explanation.

Job Description Text:
{raw_text}"""

def _fallback_parse_jd(raw_text: str) -> Dict:
    text_lower = raw_text.lower()
    found_skills = [
        skill for skill in COMMON_SKILLS
        if re.search(r'\b' + re.escape(skill.lower()) + r'\b', text_lower)
    ]
    
    first_line = raw_text.strip().splitlines()[0] if raw_text.strip() else "Job Position"
    job_title = first_line[:80]

    result = {
        "job_title": job_title,
        "required_skills": found_skills[:8],
        "preferred_skills": found_skills[8:15],
        "experience_required": "",
        "education_required": "",
        "key_responsibilities": [],
        "keywords": found_skills,
    }
    return _validate_jd_result(result)

def parse_job_description(raw_text: str) -> Dict:
    client = _get_client()
    if not client:
        logger.info("Using local fallback JD parser (Groq API key not provided or invalid).")
        return _fallback_parse_jd(raw_text)

    try:
        prompt = JD_USER_PROMPT.format(raw_text=raw_text)
        raw_response = _call_groq(client, JD_SYSTEM_PROMPT, prompt)
        result = _try_parse_json(raw_response)
        if result is not None:
            return _validate_jd_result(result)

        logger.warning("Groq JD parse: first attempt returned invalid JSON, retrying...")
        strict_prompt = (
            "Your previous response was not valid JSON. "
            "Return ONLY the raw JSON object, no markdown, no explanation, no code fences.\n\n"
            + prompt
        )
        raw_response = _call_groq(client, JD_SYSTEM_PROMPT, strict_prompt)
        result = _try_parse_json(raw_response)
        if result is not None:
            return _validate_jd_result(result)
    except Exception as exc:
        logger.warning(f"Groq parse_job_description failed ({exc}). Falling back to local parser.")
        return _fallback_parse_jd(raw_text)

    return _fallback_parse_jd(raw_text)

def _validate_jd_result(result: dict) -> dict:
    defaults = {
        "job_title": "",
        "required_skills": [],
        "preferred_skills": [],
        "experience_required": "",
        "education_required": "",
        "key_responsibilities": [],
        "keywords": [],
    }

    for key, default in defaults.items():
        if key not in result or result[key] is None:
            result[key] = default
        if isinstance(default, list) and not isinstance(result[key], list):
            result[key] = default

    return result

def _validate_resume_result(result: dict) -> dict:
    defaults = {
        "name": "",
        "email": None,
        "phone": None,
        "linkedin": None,
        "github": None,
        "professional_summary": "",
        "skills": [],
        "experience": [],
        "education": [],
        "certifications": [],
        "projects": [],
        "action_verbs": [],
        "keywords": [],
    }
    for key, default in defaults.items():
        if key not in result or result[key] is None:
            result[key] = default
        if isinstance(default, list) and not isinstance(result[key], list):
            result[key] = default

    for exp in result.get("experience", []):
        if not isinstance(exp, dict):
            continue
        exp.setdefault("job_title", "")
        exp.setdefault("company", "")
        exp.setdefault("start_date", "")
        exp.setdefault("end_date", "")
        exp.setdefault("duration_months", 0)
        exp.setdefault("description", "")
        try:
            exp["duration_months"] = int(exp["duration_months"])
        except (ValueError, TypeError):
            exp["duration_months"] = 0

    for proj in result.get("projects", []):
        if not isinstance(proj, dict):
            continue
        proj.setdefault("title", "")
        proj.setdefault("description", "")
        proj.setdefault("technologies", [])

    return result