import sys
import os
from typing import Dict, Any
from core.registry.base import BaseAgent

# Import mcp_call
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from mcp_client import mcp_call

class ClientAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "client"

    @property
    def description(self) -> str:
        return "Specialist agent that retrieves client profiles, hiring preferences, and account health."

    @property
    def required_inputs(self) -> list[str]:
        return ["candidate_context"]

    @property
    def produced_outputs(self) -> list[str]:
        return ["client_context", "agent_outputs"]

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        candidate_context = state.get("candidate_context") or {}
        matched_jobs = candidate_context.get("matched_jobs") or []
        
        client_context = {}
        
        # Get unique client IDs from matching jobs
        client_ids = set()
        for job in matched_jobs:
            c_id = job.get("client_id")
            if c_id:
                client_ids.add(c_id)
                
        # Fetch account health/profile for each client via MCP
        for client_id in client_ids:
            health_data = await mcp_call("get_client_account_health", client_id=client_id)
            if health_data:
                client_context[client_id] = {
                    "profile": health_data,
                    "account_health": health_data.get("account_health_score", 100),
                    "hiring_preferences": health_data.get("hiring_preferences", [])
                }
                
        agent_outputs = state.get("agent_outputs") or {}
        agent_outputs["client"] = {
            "processed_clients_count": len(client_context),
            "clients_list": list(client_context.keys())
        }
        
        return {
            "client_context": client_context,
            "agent_outputs": agent_outputs
        }
