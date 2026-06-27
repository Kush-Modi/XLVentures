from typing import Dict, Any
from core.registry.base import BaseAgent
from knowledge.knowledge_service import KnowledgeService

class KnowledgeAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.service = KnowledgeService()

    @property
    def name(self) -> str:
        return "knowledge"

    @property
    def description(self) -> str:
        return "Knowledge agent retrieving candidate recruiter logs, emails, meetings, and CRM updates."

    @property
    def required_inputs(self) -> list[str]:
        return []

    @property
    def produced_outputs(self) -> list[str]:
        return ["knowledge_context", "agent_outputs"]

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        candidate_data = state.get("candidate_data") or {}
        candidate_id = state.get("candidate_id") or candidate_data.get("id")
        
        # Build search query from candidate skills and title
        skills_str = ", ".join(candidate_data.get("skills", [])) if candidate_data.get("skills") else ""
        pos = candidate_data.get("current_position", "")
        query_text = f"Placements and interactions for {candidate_data.get('name', 'candidate')} {pos} {skills_str}"
        
        # Run hybrid search
        ranked_items = self.service.hybrid_search(
            query_text=query_text,
            candidate_id=candidate_id
        )
        
        # Structure context for backward-compatibility and explainability
        knowledge_context = {
            "ranked_items": ranked_items,
            "notes_count": len(ranked_items),
            "meeting_notes": [item for item in ranked_items if item.get("type") == "meeting_note"],
            "emails": [item for item in ranked_items if item.get("type") == "email"],
            "crm_updates": [item for item in ranked_items if item.get("type") == "crm_update"],
            "recruiter_notes": [item for item in ranked_items if item.get("type") == "recruiter_note"],
            "playbooks": [item for item in ranked_items if item.get("type") == "playbook"]
        }
        
        agent_outputs = state.get("agent_outputs") or {}
        agent_outputs["knowledge"] = {
            "notes_count": len(ranked_items),
            "status": "populated" if ranked_items else "empty"
        }
        
        return {
            "knowledge_context": knowledge_context,
            "agent_outputs": agent_outputs
        }


