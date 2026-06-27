import os
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import graph
import redis_client
from redis_client import get_hitl_pending, resolve_hitl, cache_get
from supabase_client import supabase
from langgraph.types import Command
from memory.feedback_manager import FeedbackManager

app = FastAPI(title="NBA Recruiter Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models ---

class AnalyzeRequest(BaseModel):
    candidate_id: str

class HITLResponse(BaseModel):
    session_id: str
    decision: str  # approved or rejected

class OutcomeRequest(BaseModel):
    recommendation_id: str
    outcome: str  # success or failure
    notes: Optional[str] = None

class CandidateCreate(BaseModel):
    name: str
    email: Optional[str] = None
    current_position: str
    experience_years: int
    location: str
    skills: List[str] = []
    resume_text: Optional[str] = ""
    notice_period_days: Optional[int] = 30
    salary_expectation: Optional[int] = None
    available: Optional[bool] = True

class ClientCreate(BaseModel):
    name: str
    industry: Optional[str] = "Technology"
    account_health: Optional[int] = 100

class JobCreate(BaseModel):
    client_id: str
    title: str
    required_skills: List[str] = []
    location: str
    salary_range: Optional[str] = "15-25 LPA"
    description_text: Optional[str] = ""

# --- Routes ---

@app.get("/health")
def health():
    return {"status": "ok", "mcp": "recruiter-mcp", "agent": "LangGraph"}


@app.post("/analyze")
async def analyze_candidate(req: AnalyzeRequest):
    """Trigger the LangGraph agent. Runs until HITL interrupt or completion, checking for cached decisions first."""
    # Check if this candidate was already evaluated (approved or rejected) to prevent duplicate workflow runs
    cached_nba = cache_get(f"nba:{req.candidate_id}")
    if cached_nba:
        print(f"\n>>> [API GATEWAY] Candidate '{req.candidate_id}' already has a cached evaluation ({cached_nba.get('status')}). Skipping graph run.")
        return {
            "status": "already_evaluated",
            "session_id": cached_nba.get("session_id"),
            "candidate": {
                "id": req.candidate_id,
                "name": cached_nba.get("candidate_name")
            },
            "recommendation": cached_nba.get("action"),
            "reasoning": cached_nba.get("reasoning"),
            "confidence": cached_nba.get("confidence"),
            "nba_status": cached_nba.get("status"),
        }
        
    session_id = f"session_{req.candidate_id}_{os.urandom(4).hex()}"
    config = {"configurable": {"thread_id": session_id}}
    
    try:
        # Kick off graph (runs until interrupt() or END)
        result = await graph.ainvoke(
            {
                "candidate_id": req.candidate_id,
                "candidate_data": {},
                "matched_jobs": [],
                "top_recommendation": {},
                "reasoning": "",
                "confidence": 0.0,
                "hitl_status": "",
                "session_id": session_id,
            },
            config=config,
        )
        
        # Check if graph is waiting on an interrupt or finished
        state = await graph.aget_state(config)
        is_pending = bool(state.next)
        
        return {
            "status": "awaiting_approval" if is_pending else "no_match_found",
            "session_id": session_id,
            "candidate": result.get("candidate_data"),
            "recommendation": result.get("top_recommendation"),
            "reasoning": result.get("reasoning"),
            "confidence": result.get("confidence"),
        }
    except Exception as e:
        import sys
        sys.stderr.write(f"Error in /analyze for session {session_id}: {e}\n")
        raise HTTPException(
            status_code=500,
            detail=f"Candidate analysis failed due to system outage/error: {str(e)}"
        )


@app.get("/hitl/pending/{session_id}")
def get_pending_hitl(session_id: str):
    """Frontend polls this to show the 'Approve/Reject' card."""
    pending = get_hitl_pending(session_id)
    if not pending:
        return {"status": "not_found"}
    return {"status": "pending", "data": pending}

@app.post("/hitl/respond")
async def respond_hitl(req: HITLResponse):
    """Recruiter approves/rejects. Resumes the interrupted LangGraph agent."""
    config = {"configurable": {"thread_id": req.session_id}}
    
    # Check if the thread is actually interrupted and waiting for input
    state = await graph.aget_state(config)
    if not state.next:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400, 
            detail=f"Session '{req.session_id}' is not in a pending approval state (it may have already completed or bypassed approval)."
        )
    
    # Write decision to Redis
    resolve_hitl(req.session_id, req.decision)
    
    # Resume graph from interrupt with Command(resume=...)
    result = await graph.ainvoke(
        Command(resume={"decision": req.decision}),
        config=config,
    )
    
    return {
        "status": result.get("hitl_status"),
        "action": result.get("top_recommendation"),
        "reasoning": result.get("reasoning"),
    }

@app.get("/nba/queue")
def get_nba_queue():
    """Get cached NBA actions for the dashboard."""
    actions = []
    for key in redis_client.r.scan_iter(match="nba:*"):
        key_str = key.decode() if isinstance(key, bytes) else key
        data = cache_get(key_str)
        # Filter and only show approved recruiter recommendations in the active NBA queue
        if data and data.get("status") == "approved":
            actions.append(data)
    
    # Sort by confidence desc
    actions.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return {"actions": actions}

@app.get("/logs/{session_id}")
def get_session_logs_endpoint(session_id: str):
    """Retrieve execution logs for a session from Redis."""
    from redis_client import get_session_logs
    logs = get_session_logs(session_id)
    return {"logs": logs or []}

@app.get("/candidates")
def list_candidates():
    result = supabase.table("candidates").select("*").execute()
    return result.data or []

@app.post("/candidates")
def create_candidate(req: CandidateCreate):
    import uuid
    candidate_id = str(uuid.uuid4())
    
    # Pack notice period and salary expectation into resume text so agents can process them
    full_resume = req.resume_text or ""
    if req.notice_period_days:
        full_resume += f"\nNotice Period: {req.notice_period_days} days."
    if req.salary_expectation:
        full_resume += f"\nSalary Expectation: ${req.salary_expectation}."
        
    payload = {
        "id": candidate_id,
        "name": req.name,
        "email": req.email,
        "current_position": req.current_position,
        "experience_years": req.experience_years,
        "location": req.location,
        "skills": req.skills,
        "resume_text": full_resume,
        "status": "available"
    }
    result = supabase.table("candidates").insert(payload).execute()
    return {"status": "created", "data": result.data or []}

@app.post("/clients")
def create_client(req: ClientCreate):
    import uuid
    from datetime import date
    client_id = str(uuid.uuid4())
    payload = {
        "id": client_id,
        "name": req.name,
        "industry": req.industry,
        "account_health": req.account_health,
        "last_contact_date": date.today().isoformat(),
        "open_roles_count": 0
    }
    result = supabase.table("clients").insert(payload).execute()
    return {"status": "created", "data": result.data or []}

@app.post("/jobs")
def create_job(req: JobCreate):
    import uuid
    job_id = str(uuid.uuid4())
    payload = {
        "id": job_id,
        "client_id": req.client_id,
        "title": req.title,
        "required_skills": req.required_skills,
        "location": req.location,
        "salary_range": req.salary_range,
        "description_text": req.description_text,
        "status": "open"
    }
    result = supabase.table("job_descriptions").insert(payload).execute()
    
    # Increment open roles count in clients table
    try:
        current_client = supabase.table("clients").select("open_roles_count").eq("id", req.client_id).execute()
        if current_client.data:
            new_count = (current_client.data[0].get("open_roles_count") or 0) + 1
            supabase.table("clients").update({"open_roles_count": new_count}).eq("id", req.client_id).execute()
    except Exception:
        pass
        
    return {"status": "created", "data": result.data or []}

@app.get("/clients")
def list_clients():
    result = supabase.table("clients").select("*").execute()
    return result.data or []

@app.get("/jobs")
def list_jobs():
    result = supabase.table("job_descriptions").select("*, clients(name)").execute()
    return result.data or []

@app.post("/analyze/outcome")
def log_outcome(req: OutcomeRequest):
    """Record the outcome of a recommendation placement (success or failure) to feedback memory."""
    try:
        res = FeedbackManager.log_placement_outcome(
            recommendation_id=req.recommendation_id,
            outcome=req.outcome,
            notes=req.notes
        )
        return {"status": "recorded", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record outcome: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)