from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class ComponentScores(BaseModel):
    formatting: float
    keywords: float
    content: float
    skill_validation: float
    ats_compatibility: float

class JDComparison(BaseModel):
    match_percentage: float
    semantic_similarity: float
    matched_keywords: List[str]
    missing_keywords: List[str]
    skills_gap: List[str]

class SkillValidationDetails(BaseModel):
    validated: List[Dict[str, Any]] = Field(default_factory=list)       # [{'skill': str, 'projects': [str]}]
    unvalidated: List[str] = Field(default_factory=list)                # ['Flask', 'A/B Testing', ...]
    total: int = 0
    validated_count: int = 0
    validation_pct: float = 0.0

class IssueDetail(BaseModel):
    issue_title: str
    severity_level: str
    ats_impact: str
    explanation: str
    where_it_appears: str
    how_to_fix: str
    action_items: List[str] = []
    example_improvement: str

class AnalysisResponse(BaseModel):
    ATS_score: float
    component_scores: ComponentScores
    issues_summary: List[str]
    detailed_feedback: List[IssueDetail]
    jd_match_analysis: Optional[JDComparison] = None
    skill_validation_details: Optional[SkillValidationDetails] = None

    ats_score: float
    keyword_match: float = 0.0
    missing_keywords: List[str] = Field(default_factory=list)
    matched_keywords: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    critical_issues: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    jd_comparison: Optional[JDComparison] = None
    warnings: List[str] = Field(default_factory=list)
    interpretation: str = ""


class LoginEvent(BaseModel):
    id: Optional[str] = None
    user_id: str
    email: str = ""
    provider: str = ""
    event_type: str = "login"
    created_at: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OwnerAnalysisRecord(BaseModel):
    id: Optional[str] = None
    user_id: str
    user_email: str = ""
    filename: str = ""
    ats_score: float = 0.0
    keyword_match: float = 0.0
    created_at: str = ""
    resume_text: str = ""
    job_description: str = ""
    analysis_result: Dict[str, Any] = Field(default_factory=dict)


class OwnerDashboardResponse(BaseModel):
    login_events: List[LoginEvent] = Field(default_factory=list)
    analyses: List[OwnerAnalysisRecord] = Field(default_factory=list)
