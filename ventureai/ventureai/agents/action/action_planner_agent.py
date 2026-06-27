import sys
import os
import json
from typing import Dict, Any
from core.registry.base import BaseAgent

# Import core elements
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from mcp_client import mcp_call
from core.llm_client import llm, MatchRecommendation
from explainability.scoring import DecisionScorer
from explainability.formatter import ExplainabilityFormatter


class ActionPlannerAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "action"

    @property
    def description(self) -> str:
        return "Specialist agent that scores candidate fit, runs structured evaluation, and creates the match recommendation."

    @property
    def required_inputs(self) -> list[str]:
        return ["candidate_data", "matched_jobs"]

    @property
    def produced_outputs(self) -> list[str]:
        return ["top_recommendation", "reasoning", "confidence", "agent_outputs"]

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        candidate_data = state.get("candidate_data") or {}
        matched_jobs = state.get("matched_jobs") or []
        candidate_id = state.get("candidate_id")
        
        if not candidate_data or not matched_jobs:
            reasoning = "No matching open roles found."
            return {
                "top_recommendation": {},
                "reasoning": reasoning,
                "confidence": 0.0,
                "agent_outputs": {
                    "action": {
                        "success": False,
                        "reason": "No candidate data or matched jobs found."
                    }
                }
            }
            
        # Retrieve placement history via MCP tool
        placements = await mcp_call("get_placement_history", candidate_id=candidate_id)
        if not placements:
            placements = []
            
        # Format the context messages for compatibility
        messages = state.get("messages") or []
        history_msgs = [msg.content for msg in messages if hasattr(msg, "content")]
        if not history_msgs:
            history_msgs = [f"Analyze candidate profile for candidate ID: {candidate_id}"]
            
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
{history_msgs}

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
        except Exception as e:
            # Fallback to default match if LLM structured output fails
            fallback_job = matched_jobs[0]
            client_name = "Client"
            if "clients" in fallback_job and isinstance(fallback_job["clients"], dict):
                client_name = fallback_job["clients"].get("name", "Client")
            elif fallback_job.get("client_name"):
                client_name = fallback_job.get("client_name")
                
            parsed = {
                "job_id": fallback_job["id"],
                "job_title": fallback_job["title"],
                "client_name": client_name,
                "client_id": fallback_job["client_id"],
                "confidence": fallback_job.get("match_score", 0.5),
                "reasoning": f"Strong skill match: {fallback_job.get('match_score', 0):.0%} overlap"
            }

        # Find job description details in matched_jobs
        job_data = next((j for j in matched_jobs if j.get("id") == parsed["job_id"]), matched_jobs[0] if matched_jobs else {})

        # Fetch client info dynamically via MCP tool
        try:
            client_data = await mcp_call("get_client_account_health", client_id=parsed["client_id"]) or {}
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to fetch client account health for rules context: {e}\n")
            client_data = {}

        # Fetch planner memory context
        from memory.planner_memory import PlannerMemory
        try:
            memory_context = PlannerMemory.get_memory_context(
                candidate_id=candidate_id,
                client_id=parsed["client_id"],
                job_id=parsed["job_id"]
            )
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to fetch planner memory context: {e}\n")
            memory_context = {}

        # Run Business Rules Engine
        from business_rules.engine import BusinessRulesEngine
        from business_rules.evaluator import RuleEvaluator
        
        try:
            # Build rules execution context
            rule_context = RuleEvaluator.build_context(
                candidate=candidate_data,
                client=client_data,
                job=job_data,
                extra={
                    "candidate_rejected_recently": memory_context.get("failure_rate", 0.0) > 0.0 or any(h.get("decision") == "rejected" for h in memory_context.get("history_trace", [])),
                    "candidate_already_submitted": any(h.get("decision") == "approved" for h in memory_context.get("history_trace", [])),
                }
            )
            rules_engine = BusinessRulesEngine()
            business_rules_res = rules_engine.run(rule_context)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to run business rules engine: {e}\n")
            business_rules_res = {}

        # Calculate final Decision Intelligence Confidence and build Evidence Tree
        knowledge_context = state.get("knowledge_context") or {}
        ranked_items = knowledge_context.get("ranked_items", [])
        
        client_health = float(client_data.get("account_health", 60)) / 100.0
        
        # Calculate Priority/Urgency Score
        desc_text = str(job_data.get("description_text", "")).lower()
        title_text = str(job_data.get("title", "")).lower()
        if "critical" in desc_text or "critical" in title_text or "urgent" in desc_text or "urgent" in title_text:
            priority_urgency_score = 1.0
        elif "high" in desc_text or "high" in title_text:
            priority_urgency_score = 0.8
        elif "medium" in desc_text:
            priority_urgency_score = 0.5
        else:
            priority_urgency_score = 0.3

        decision = DecisionScorer.calculate_decision(
            candidate_fit_score=parsed["confidence"],
            ranked_knowledge_items=ranked_items,
            candidate_name=candidate_data.get("name", "Candidate"),
            client_name=parsed["client_name"],
            jd_title=parsed["job_title"],
            business_rules_res=business_rules_res,
            memory_context=memory_context,
            client_health=client_health,
            priority_urgency_score=priority_urgency_score
        )
        
        planner_steps = [
            "Task Planning initiated",
            "Fetched candidate profile context",
            "Executed semantic match against open jobs",
            "Fetched client account details & health metrics",
            "Loaded history from Planner Memory feedback logs",
            "Executed Business Rules Engine validation",
            "Compiled final multi-signal decision confidence score"
        ]
        
        explanation = ExplainabilityFormatter.format_explanation(decision, ranked_items, planner_steps)
        
        # Override the confidence and append visual explainability to reasoning
        final_conf = decision["final_confidence"]
        parsed["confidence"] = final_conf
        parsed["decision_confidence"] = final_conf
        parsed["reasoning"] = f"{parsed['reasoning']}\n\n{explanation['markdown_explanation']}"
        parsed["knowledge_trace"] = explanation["knowledge_trace"]
        parsed["retrieval_trace"] = explanation["retrieval_trace"]
        parsed["planner_trace"] = explanation["planner_trace"]
        parsed["decision_trace"] = explanation["decision_trace"]
        parsed["business_rule_trace"] = explanation["business_rule_trace"]
        parsed["memory_trace"] = explanation["memory_trace"]
        parsed["evidence_tree"] = explanation["evidence_tree"]
        parsed["confidence_breakdown"] = explanation["confidence_breakdown"]
        
        agent_outputs = state.get("agent_outputs") or {}
        agent_outputs["action"] = {
            "success": True,
            "job_title": parsed["job_title"],
            "client_name": parsed["client_name"],
            "confidence": final_conf,
            "knowledge_trace": explanation["knowledge_trace"],
            "retrieval_trace": explanation["retrieval_trace"],
            "planner_trace": explanation["planner_trace"],
            "decision_trace": explanation["decision_trace"],
            "business_rule_trace": explanation["business_rule_trace"],
            "memory_trace": explanation["memory_trace"],
        }
        
        return {
            "top_recommendation": parsed,
            "reasoning": parsed["reasoning"],
            "confidence": final_conf,
            "knowledge_trace": explanation["knowledge_trace"],
            "retrieval_trace": explanation["retrieval_trace"],
            "planner_trace": explanation["planner_trace"],
            "decision_trace": explanation["decision_trace"],
            "business_rule_trace": explanation["business_rule_trace"],
            "memory_trace": explanation["memory_trace"],
            "evidence_tree": explanation["evidence_tree"],
            "confidence_breakdown": explanation["confidence_breakdown"],
            "agent_outputs": agent_outputs
        }


