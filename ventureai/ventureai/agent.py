import os
import json
from typing import TypedDict, Annotated, List
from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, ToolMessage

from mcp_client import mcp_call
from redis_client import set_hitl_pending, cache_set, log_session
from supabase_client import supabase

def log_event(session_id: str, message: str):
    print(message)
    if session_id:
        log_session(session_id, message)

# --- Schema Definition for Structured Output ---
class MatchRecommendation(BaseModel):
    job_id: str = Field(description="UUID of the best matching job")
    job_title: str = Field(description="Job title")
    client_name: str = Field(description="Client company name")
    client_id: str = Field(description="UUID of the client")
    confidence: float = Field(description="Match confidence score between 0.0 and 1.0")
    reasoning: str = Field(description="Detailed evaluation including Strengths, Evidence from placements history, Gaps, and a Pitch Angle")

# LLM
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.2,
)

# State
class AgentState(TypedDict):
    candidate_id: str
    messages: list
    candidate_data: dict
    matched_jobs: List[dict]
    top_recommendation: dict
    reasoning: str
    confidence: float
    hitl_status: str
    session_id: str

# --- Langchain Proxy Tools (for LLM tool binding description) ---
@tool
def get_candidate_profile(candidate_id: str) -> str:
    """Fetch the candidate profile by their unique ID, returning their name, email, skills, experience, current position, and resume."""
    pass

@tool
def search_job_descriptions(query_skills: str) -> str:
    """Search open job descriptions by matching comma-separated skill keywords. Returns a list of jobs."""
    pass

@tool
def get_placement_history(candidate_id: str = None, client_id: str = None) -> str:
    """Fetch the past placement and hire records for a specific candidate or client from the memory layer."""
    pass

# --- Autonomous Node Definitions (Option 2 - Current Active Agent) ---

# --- Autonomous Node Definitions (Option 2 - Current Active Agent) ---

async def run_llm_agent(state: AgentState):
    """Coordinator LLM node. Examines messages, decides whether to call tools to gather candidate/job info."""
    candidate_id = state.get("candidate_id")
    session_id = state.get("session_id")
    
    if not candidate_id:
        log_event(session_id, "\n>>> [AGENT COORDINATOR] Warning: run_llm_agent invoked without candidate_id.")
        return {"messages": []}
        
    log_event(session_id, f"\n>>> [AGENT COORDINATOR] Evaluating candidate ID: {candidate_id}")
    
    messages = state.get("messages") or []
    if not messages:
        messages = [HumanMessage(content=f"Analyze candidate profile for candidate ID: {candidate_id}")]
        
    tools = [get_candidate_profile, search_job_descriptions, get_placement_history]
    llm_with_tools = llm.bind_tools(tools)
    
    system_instruction = SystemMessage(
        content="You are an expert recruitment coordinator agent.\n"
        "Your task is to recommendation the single best matching job for the candidate.\n"
        "To do this, follow these steps:\n"
        "1. Call `get_candidate_profile` with the candidate_id to read their skills.\n"
        "2. Call `search_job_descriptions` using their skills to find open positions.\n"
        "3. Optionally call `get_placement_history` for the candidate to review past matches.\n"
        "4. Once you have all the facts, stop calling tools. The coordinator will format the final recommendation."
    )
    
    response = llm_with_tools.invoke([system_instruction] + messages)
    
    if response.tool_calls:
        for tc in response.tool_calls:
            log_event(session_id, f"    - LLM requested tool call: {tc['name']} with args: {tc['args']}")
    else:
        log_event(session_id, "    - LLM decided no further tools are needed. Proceeding to format recommendation.")
        
    return {"messages": messages + [response]}

async def call_tools(state: AgentState):
    """Custom executor node that runs the requested MCP tools."""
    messages = state["messages"]
    last_message = messages[-1]
    session_id = state.get("session_id")
    
    tool_outputs = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        args = tool_call["args"]
        
        log_event(session_id, f"    >>> [MCP CLIENT] Executing {tool_name} with parameters: {args}")
        # Execute tool via the MCP client
        res = await mcp_call(tool_name, **args)
        log_event(session_id, f"    <<< [MCP CLIENT] Finished execution of {tool_name}.")
        
        tool_outputs.append(
            ToolMessage(
                content=json.dumps(res, default=str),
                tool_call_id=tool_call["id"],
                name=tool_name
            )
        )
    return {"messages": messages + tool_outputs}

async def format_recommendation(state: AgentState):
    """Extracts tool outputs from chat history, invokes structured LLM to populate state recommendation fields."""
    session_id = state.get("session_id")
    log_event(session_id, ">>> [RECOMMENDATION FORMATTER] Extracting tool data & generating structured evaluation...")
    history_messages = state["messages"]
    
    candidate_data = {}
    matched_jobs = []
    
    for msg in history_messages:
        if isinstance(msg, ToolMessage):
            try:
                data = json.loads(msg.content)
                if msg.name == "get_candidate_profile":
                    candidate_data = data
                elif msg.name == "search_job_descriptions":
                    matched_jobs = data
            except Exception:
                pass
                
    if not candidate_data or not matched_jobs:
        log_event(session_id, "    ! No candidate data or matching jobs found in analysis history. Terminating.")
        return {
            "top_recommendation": {},
            "reasoning": "No matching open roles found.",
            "confidence": 0.0,
            "candidate_data": candidate_data,
            "matched_jobs": matched_jobs,
        }
        
    prompt = f"""
You are an expert executive recruiter. Perform a detailed, highly professional match analysis between the candidate and the matching jobs.

Candidate Profile:
- Name: {candidate_data.get('name')}
- Current Position: {candidate_data.get('current_position', 'N/A')}
- Skills: {', '.join(candidate_data.get('skills', []))}
- Experience: {candidate_data.get('experience_years', 0)} years
- Resume: {candidate_data.get('resume_text', 'N/A')}

Matching Open Jobs:
{json.dumps(matched_jobs, indent=2, default=str)}

Analysis Context History:
{[msg.content for msg in history_messages if not isinstance(msg, SystemMessage)]}

Pick the SINGLE best job match. In the 'confidence' field, calculate the score mathematically based on this rubric:
1. SKILL ALIGNMENT (Max 0.40): Calculate the ratio of candidate matching skills to the job required skills.
2. EXPERIENCE FIT (Max 0.30): Compare candidate experience years to job requirements (Full 0.30 if equal/greater, partial if less).
3. PLACEMENT EVIDENCE (Max 0.20): Award up to 0.20 if candidate has successful historical placements in this role or at this client.
4. LOCATION & STATUS (Max 0.10): Award 0.10 if locations match (Bangalore/Remote etc) and they are available.

Sum these 4 components to calculate the final 'confidence' score (between 0.0 and 1.0).

In the 'reasoning' field, format your output as a professional report using this exact template structure:
[MATCH FIT]: [A 2-sentence summary of why the candidate is a fit for the role]
[KEY STRENGTHS]:
- [Bullet 1: Direct skill/experience alignment]
- [Bullet 2: Specific context or project match]
[PLACEMENT EVIDENCE]: [Reference the past placement records for this candidate or client, explaining how previous success reduces hiring risk]
[GAPS & MITIGATION]: [Specify any missing skills or experience gaps, and explain how the candidate can adapt or upskill]
[RECRUITER PITCH HOOK]: [A one-sentence persuasive statement the recruiter can read to pitch this candidate to the client's hiring manager]
"""
    try:
        structured_llm = llm.with_structured_output(MatchRecommendation)
        result = structured_llm.invoke(prompt)
        parsed = {
            "job_id": result.job_id,
            "job_title": result.job_title,
            "client_name": result.client_name,
            "client_id": result.client_id,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
        }
        log_event(session_id, f"    - Structured Recommendation Generated: {parsed['job_title']} at {parsed['client_name']} (Confidence: {parsed['confidence']})")
    except Exception as e:
        log_event(session_id, f"    ! Structured LLM invocation failed: {e}. Falling back to default match.")
        parsed = {
            "job_id": matched_jobs[0]["id"],
            "job_title": matched_jobs[0]["title"],
            "client_name": matched_jobs[0]["clients"]["name"],
            "client_id": matched_jobs[0]["client_id"],
            "confidence": matched_jobs[0].get("match_score", 0.5),
            "reasoning": f"Strong skill match: {matched_jobs[0].get('match_score', 0):.0%} overlap"
        }
        
    return {
        "top_recommendation": parsed,
        "reasoning": parsed.get("reasoning", ""),
        "confidence": parsed.get("confidence", 0.5),
        "candidate_data": candidate_data,
        "matched_jobs": matched_jobs,
    }

def hitl_gate(state: AgentState):
    """Node: HITL interrupt. Pauses execution until recruiter responds."""
    rec = state["top_recommendation"]
    session_id = state["session_id"]
    
    log_event(session_id, f"\n>>> [HITL APPROVAL GATE] Saving pending recommendation for {state['candidate_data'].get('name')} to Redis...")
    set_hitl_pending(session_id, {
        "candidate_id": state["candidate_id"],
        "candidate_name": state["candidate_data"].get("name"),
        "recommended_action": f"Pitch {state['candidate_data'].get('name')} to {rec.get('client_name')} for {rec.get('job_title')}",
        "reasoning": state["reasoning"],
        "confidence": state["confidence"],
        "job_id": rec.get("job_id"),
        "client_id": rec.get("client_id"),
    })
    
    log_event(session_id, "    !!! GRAPH PAUSED. Awaiting recruiter response (Approve/Reject)...")
    human_response = interrupt({
        "session_id": session_id,
        "message": f"Approve pitching {state['candidate_data'].get('name')} to {rec.get('client_name')}?",
        "reasoning": state["reasoning"],
        "confidence": state["confidence"],
    })
    
    log_event(session_id, f"    <<< GRAPH RESUMED. Recruiter decision received: {human_response.get('decision', 'rejected').upper()}")
    return {"hitl_status": human_response.get("decision", "rejected")}

async def execute_action(state: AgentState):
    """Node: Log recruiter action to Supabase and cache finalised Next Best Action."""
    decision = state["hitl_status"]
    session_id = state["session_id"]
    log_event(session_id, f"\n>>> [ACTION EXECUTION] Processing final decision: {decision}")
    
    rec = state["top_recommendation"]
    
    # Log the action (both approval and rejection) to Supabase so the system learns
    log_event(session_id, f"    - Logging recruiter action ({decision}) to Supabase 'recruiter_actions' table...")
    await mcp_call(
        "log_recruiter_action",
        action_type="pitch_candidate",
        target_id=state["candidate_id"],
        target_type="candidate",
        reason=state["reasoning"],
        recruiter_decision=decision,
    )
    
    if decision == "approved":
        log_event(session_id, f"    - Caching finalized Next Best Action to Redis key: nba:{state['candidate_id']}")
        cache_set(f"nba:{state['candidate_id']}", {
            "candidate_id": state["candidate_id"],
            "candidate_name": state["candidate_data"].get("name"),
            "action": rec,
            "reasoning": state["reasoning"],
            "confidence": state["confidence"],
            "status": "approved",
            "session_id": state["session_id"],
        }, ttl=600)
    else:
        log_event(session_id, f"    - Action rejected. Caching rejection status to Redis key: nba:{state['candidate_id']}")
        cache_set(f"nba:{state['candidate_id']}", {
            "candidate_id": state["candidate_id"],
            "candidate_name": state["candidate_data"].get("name"),
            "action": rec,
            "reasoning": state["reasoning"],
            "confidence": state["confidence"],
            "status": "rejected",
            "session_id": state["session_id"],
        }, ttl=600)
        
    log_event(session_id, ">>> [WORKFLOW COMPLETED SUCCESSFULLY]")
    return {"hitl_status": "executed" if decision == "approved" else "rejected"}

# --- Graph Routing Logic ---

def route_agent(state: AgentState):
    """Routes execution: tool executor, final formatting, or end."""
    messages = state["messages"]
    last_message = messages[-1]
    
    if last_message.tool_calls:
        return "call_tools"
    return "format"

def route_after_score(state: AgentState):
    rec = state.get("top_recommendation", {})
    if not rec or not rec.get("job_id"):
        return END
    return "hitl"

def route_after_hitl(state: AgentState):
    # Always route to execute to log the decision (whether approved or rejected)
    return "execute"

# --- Build Autonomous Graph ---

builder = StateGraph(AgentState)
builder.add_node("agent", run_llm_agent)
builder.add_node("call_tools", call_tools)
builder.add_node("format", format_recommendation)
builder.add_node("hitl", hitl_gate)
builder.add_node("execute", execute_action)

builder.set_entry_point("agent")
builder.add_conditional_edges("agent", route_agent, {"call_tools": "call_tools", "format": "format"})
builder.add_edge("call_tools", "agent")
builder.add_conditional_edges("format", route_after_score, {"hitl": "hitl", END: END})
builder.add_conditional_edges("hitl", route_after_hitl, {"execute": "execute", END: END})
builder.add_edge("execute", END)

memory = MemorySaver()
graph = builder.compile(checkpointer=memory)

# --- BACKUP: Legacy DAG Graph Implementation (For Reference) ---

async def legacy_fetch_candidate(state: AgentState):
    candidate_id = state["candidate_id"]
    session_id = state.get("session_id") or f"session_{candidate_id}_{os.urandom(4).hex()}"
    cand = await mcp_call("get_candidate_profile", candidate_id=candidate_id)
    if not cand:
        return {"candidate_data": {}, "matched_jobs": [], "session_id": session_id}
    skills = ",".join(cand.get("skills", []))
    jobs = await mcp_call("search_job_descriptions", query_skills=skills)
    cache_set(f"analysis:{candidate_id}", {"candidate": cand, "jobs": jobs}, ttl=300)
    return {"candidate_data": cand, "matched_jobs": jobs or [], "session_id": session_id}

async def legacy_score_and_reason(state: AgentState):
    candidate = state["candidate_data"]
    jobs = state["matched_jobs"]
    if not candidate or not jobs:
        return {"top_recommendation": {}, "reasoning": "No matching open roles found.", "confidence": 0.0}
    history = await mcp_call("get_placement_history", candidate_id=state["candidate_id"])
    prompt = f"Analyze Candidate: {candidate.get('name')} against open jobs {jobs}. Past Placements: {history}."
    try:
        structured_llm = llm.with_structured_output(MatchRecommendation)
        result = structured_llm.invoke(prompt)
        parsed = {
            "job_id": result.job_id,
            "job_title": result.job_title,
            "client_name": result.client_name,
            "client_id": result.client_id,
            "confidence": result.confidence,
            "reasoning": result.reasoning
        }
    except Exception:
        parsed = {"job_id": jobs[0]["id"], "job_title": jobs[0]["title"], "client_name": jobs[0]["clients"]["name"], "client_id": jobs[0]["client_id"], "confidence": 0.5, "reasoning": "Fallback match"}
    return {"top_recommendation": parsed, "reasoning": parsed.get("reasoning", ""), "confidence": parsed.get("confidence", 0.5)}

legacy_builder = StateGraph(AgentState)
legacy_builder.add_node("fetch", legacy_fetch_candidate)
legacy_builder.add_node("score", legacy_score_and_reason)
legacy_builder.add_node("hitl", hitl_gate)
legacy_builder.add_node("execute", execute_action)
legacy_builder.set_entry_point("fetch")
legacy_builder.add_edge("fetch", "score")
legacy_builder.add_conditional_edges("score", route_after_score, {"hitl": "hitl", END: END})
legacy_builder.add_conditional_edges("hitl", route_after_hitl, {"execute": "execute", END: END})
legacy_builder.add_edge("execute", END)

legacy_graph = legacy_builder.compile(checkpointer=memory)