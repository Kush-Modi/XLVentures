import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import graph
import redis_client
from redis_client import get_hitl_pending, resolve_hitl, cache_get
from supabase_client import supabase
from langgraph.types import Command

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

@app.get("/clients")
def list_clients():
    result = supabase.table("clients").select("*").execute()
    return result.data or []

@app.get("/jobs")
def list_jobs():
    result = supabase.table("job_descriptions").select("*, clients(name)").execute()
    return result.data or []

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)