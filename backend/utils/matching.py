import re
from typing import Dict, List, Set

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    import difflib
    HAS_RAPIDFUZZ = False

def normalize_skill(skill: str) -> str:
    """
    Normalizes a skill string by lowercasing, stripping, and removing special characters/whitespace.
    e.g. 'Node.js' -> 'nodejs', 'React JS' -> 'reactjs'
    """
    if not skill:
        return ""
    skill_clean = skill.lower().strip()
    skill_clean = re.sub(r'[\.\-\s\/]+', '', skill_clean)
    return skill_clean

def fuzzy_match_keywords(
    resume_terms: List[str],
    jd_keywords: List[str],
    threshold: float = 80.0
) -> Dict[str, List[str]]:
    """
    Fuzzy matches resume terms against job description keywords.
    Returns a dict with 'matched' and 'missing' lists.
    """
    matched: Set[str] = set()
    missing: Set[str] = set()

    # Pre-normalize resume terms for faster lookup
    resume_normalized = {normalize_skill(term) for term in resume_terms if term}
    
    for jd_kw in jd_keywords:
        if not jd_kw:
            continue
        jd_kw_norm = normalize_skill(jd_kw)
        
        # 1. Exact / normalized match
        if jd_kw_norm in resume_normalized:
            matched.add(jd_kw)
            continue
        
        # 2. Substring match
        found_substring = False
        for r_term in resume_terms:
            r_norm = normalize_skill(r_term)
            if jd_kw_norm in r_norm or r_norm in jd_kw_norm:
                matched.add(jd_kw)
                found_substring = True
                break
        if found_substring:
            continue

        # 3. Fuzzy match
        best_ratio = 0.0
        for r_term in resume_terms:
            r_norm = normalize_skill(r_term)
            if HAS_RAPIDFUZZ:
                ratio = fuzz.token_sort_ratio(jd_kw_norm, r_norm)
            else:
                # SequenceMatcher ratio returns float between 0.0 and 1.0; scale to 100
                ratio = difflib.SequenceMatcher(None, jd_kw_norm, r_norm).ratio() * 100
            
            if ratio > best_ratio:
                best_ratio = ratio
        
        if best_ratio >= threshold:
            matched.add(jd_kw)
        else:
            missing.add(jd_kw)

    return {
        "matched": list(matched),
        "missing": list(missing)
    }
