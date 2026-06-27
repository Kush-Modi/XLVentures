import sys
import os
from typing import Dict, Any
from core.registry.base import BaseAgent

# Import mcp_call
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from mcp_client import mcp_call

class CandidateAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "candidate"

    @property
    def description(self) -> str:
        return "Specialist agent that fetches candidate profile info and matches open job descriptions."

    @property
    def required_inputs(self) -> list[str]:
        return ["candidate_id"]

    @property
    def produced_outputs(self) -> list[str]:
        return ["candidate_context", "candidate_data", "matched_jobs", "agent_outputs"]

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        candidate_id = state.get("candidate_id")
        if not candidate_id:
            raise ValueError("Candidate ID is required for CandidateAgent.")
            
        # Fetch candidate profile details via MCP tool
        profile = await mcp_call("get_candidate_profile", candidate_id=candidate_id)
        if not profile:
            profile = {}
            
        # Normalize and extract candidate skills
        skills = profile.get("skills", [])
        skills_str = ",".join(skills) if isinstance(skills, list) else str(skills)
        
        # Search open jobs using candidate skills
        matched_jobs = []
        if skills_str:
            matched_jobs = await mcp_call("search_job_descriptions", query_skills=skills_str)
            if not matched_jobs:
                matched_jobs = []
                
        candidate_context = {
            "profile": profile,
            "skills": skills,
            "experience_years": profile.get("experience_years", 0),
            "matched_jobs": matched_jobs
        }
        
        # Log to agent outputs for explainability
        agent_outputs = state.get("agent_outputs") or {}
        agent_outputs["candidate"] = {
            "profile_fetched": bool(profile),
            "skills_count": len(skills),
            "matched_jobs_count": len(matched_jobs)
        }
        
        return {
            "candidate_context": candidate_context,
            "agent_outputs": agent_outputs,
            "candidate_data": profile,
            "matched_jobs": matched_jobs
        }
