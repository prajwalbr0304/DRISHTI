"""Case-scoped investigation assistant (Prompt 20 Part D).

A THIN orchestration surface that composes the EXISTING governed case APIs
(summary, similar-case, modus-operandi, canonical identity, graph/network, leads,
timeline) for one authorized selected case. It is NOT a second ungoverned
chatbot: free-form data questions still go through the Prompt 19 /chat engine;
this assistant maps a small set of case-scoped intents to fixed, cited actions
and returns the Prompt 19 answer contract (answer/confidence/source ids).

Facts/evidence are separated STRUCTURALLY from suggestions/hypotheses, and two
people are never asserted to be the same on embedding similarity alone —
canonical (reviewed) identity links are facts; name/embedding matches are
labelled candidate hypotheses requiring review. Cited objects can be sent to the
Investigation Board.
"""
