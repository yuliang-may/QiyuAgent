"""Specialized agents for the LacquerTutor multi-agent architecture.

Architecture:
  TriageAgent → DialogueAgent / PlanningAgent / TroubleshootingAgent

Each agent has focused instructions, a small tool set, and handoffs
to other specialists. Context flows via RunContextWrapper[LacquerTutorContext].
"""

from lacquertutor.agent.agents.triage import create_triage_agent
from lacquertutor.agent.agents.dialogue import create_dialogue_agent
from lacquertutor.agent.agents.planning import create_planning_agent
from lacquertutor.agent.agents.troubleshooting import create_troubleshooting_agent

__all__ = [
    "create_triage_agent",
    "create_dialogue_agent",
    "create_planning_agent",
    "create_troubleshooting_agent",
]
