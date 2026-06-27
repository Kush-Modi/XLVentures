import os
import json
import re
from mcp.server.fastmcp import FastMCP
from supabase_client import supabase
from redis_client import cache_get, cache_set
from langchain_groq import ChatGroq
from dotenv import load_dotenv

load_dotenv()

mcp = FastMCP("recruiter-mcp")

# Initialize LLM for semantic search within the tool
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.0, # Deterministic matching
)

@mcp.tool()
def get_candidate_profile(candidate_id: str) -> dict:
    """Get candidate profile by ID. Checks Redis cache first, then Supabase."""
    cache_key = f"cand:{candidate_id}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    
    result = supabase.table("candidates").select("*").eq("id", candidate_id).single().execute()
    data = result.data
    if data:
        cache_set(cache_key, data, ttl=600)
    return data or {}

@mcp.tool()
def get_client_account_health(client_id: str) -> dict:
    """Get client account health and metadata. Cached in Redis."""
    cache_key = f"client:{client_id}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    
    result = supabase.table("clients").select("*").eq("id", client_id).single().execute()
    data = result.data
    if data:
        cache_set(cache_key, data, ttl=600)
    return data or {}

@mcp.tool()
def search_job_descriptions(query_skills: str) -> list:
    """Search open JDs by required skills (comma-separated). Returns top 5 matches using LLM semantic scoring."""
    result = supabase.table("job_descriptions").select("*, clients(name)").eq("status", "open").execute()
    jobs = result.data or []
    if not jobs:
        return []
        
    # Prepare job summaries to optimize token usage and processing speed
    jobs_summary = []
    for job in jobs:
        jobs_summary.append({
            "job_id": job["id"],
            "title": job["title"],
            "required_skills": job.get("required_skills", []),
            "description": job.get("description_text", "")[:150]
        })
        
    prompt = f"""
You are an AI scoring system. Evaluate the match between the candidate's skills and the available jobs.
Match skills semantically (e.g. AWS = Amazon Web Services, K8s = Kubernetes, React = ReactJS, React.js = React).

Candidate Skills: {query_skills}

Available Jobs:
{json.dumps(jobs_summary, indent=2)}

Score each job from 0.0 (no match) to 1.0 (perfect semantic match).
Return ONLY a JSON list of objects, each containing 'job_id' and 'semantic_score'.
Example:
[
  {{"job_id": "...", "semantic_score": 0.95}}
]
"""
    try:
        response = llm.invoke(prompt)
        match = re.search(r'\[.*\]', response.content, re.DOTALL)
        scores = json.loads(match.group()) if match else []
        scores_map = {item["job_id"]: item["semantic_score"] for item in scores}
    except Exception as e:
        print(f"Error in LLM semantic scoring: {e}")
        scores_map = {}
        
    matched = []
    for job in jobs:
        score = scores_map.get(job["id"])
        
        # Fallback to keyword matching if LLM scoring fails or misses the job
        if score is None:
            skills_list = [s.strip().lower() for s in query_skills.split(",")]
            req_skills = [r.lower() for r in job.get("required_skills", [])]
            overlap = sum(1 for s in skills_list if s in req_skills)
            score = overlap / len(req_skills) if req_skills else 0.0
            
        if score > 0.0:
            job["match_score"] = score
            matched.append(job)
            
    # Sort descending by match score
    matched.sort(key=lambda x: x["match_score"], reverse=True)
    return matched[:5]

@mcp.tool()
def get_placement_history(candidate_id: str = None, client_id: str = None) -> list:
    """Get past placements for candidate or client from Supabase."""
    q = supabase.table("placements").select("*, candidates(name), clients(name), job_descriptions(title)")
    if candidate_id:
        q = q.eq("candidate_id", candidate_id)
    if client_id:
        q = q.eq("client_id", client_id)
    result = q.execute()
    return result.data or []

@mcp.tool()
def log_recruiter_action(action_type: str, target_id: str, target_type: str, reason: str, recruiter_decision: str) -> dict:
    """Log a recruiter action to the memory layer in Supabase."""
    payload = {
        "action_type": action_type,
        "target_id": target_id,
        "target_type": target_type,
        "reason": reason,
        "recruiter_decision": recruiter_decision,
    }
    result = supabase.table("recruiter_actions").insert(payload).execute()
    return result.data[0] if result.data else {}

if __name__ == "__main__":
    mcp.run()