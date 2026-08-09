"""Minimal RLM + capsule example."""

from pocket_agent import Agent

agent = Agent(project="example")
res = agent.run(
    """
set_goal("Demo RLM + capsule")
cap = capsule_spin(reason="skill_preview", tier="256MB")
outs = rlm_map([
    "list three risks of untrusted code on a host agent",
    "why WASM capsules improve agent safety",
], max_workers=2)
result = {"capsule": cap.get("id"), "rlm": [o.output[:200] for o in outs]}
print(result)
"""
)
print(res.summary)
