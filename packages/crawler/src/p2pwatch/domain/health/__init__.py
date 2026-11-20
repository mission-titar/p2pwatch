"""Health: whether each part of the node works.

The node tracks the health of each of its parts, its external dependencies, such as the aMule client
(an ``ExternalDependency``).
Each part has rules (a ``HealthRule``), such as "aMule does not answer".
At each check, the code records in ``NodeHealth`` whether the rule detected its case.
From its latest checks, the rule says whether the part is healthy or failing (a ``HealthState``).
For example, the status reading asks aMule for its status every minute.
Detected 3 times in a row, the client is failing: "amuled unreachable for 2 min".
Detected fewer than 2 times in the last 10, it is healthy again: "amuled reachable again".
Turning healthy takes longer than failing, so a flaky client does not alert on and off.
Before its first 3 checks, its state is unknown, and nothing is sent.
Each notification sent is checked too: whether its service took it.
A bug is no outage: the supervisor counts those of each object it rebuilds, never here.
"""
