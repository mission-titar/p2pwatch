"""Health: whether each part of the node works.

The node tracks the health of each of its parts, such as the aMule client (a ``Component``).
Each attempt a part makes gives an ``Outcome``: it worked, or it failed, and why.
A ``HealthCondition`` looks at a part's latest outcomes and says whether it is healthy or failing.
For example, the status reading asks aMule for its status every minute.
After 3 readings in a row without an answer, the client is failing: "amuled unreachable for 2 min".
It is healthy again once fewer than 2 of its last 10 readings went unanswered: "reachable again".
Recovering takes more than failing, so a flaky client does not alert on and off.
Before its first 3 readings, its health is unknown, and nothing is sent.
Later, the same model will restart a part that keeps crashing.
"""
