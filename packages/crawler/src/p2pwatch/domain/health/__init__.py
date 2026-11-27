"""Health: whether what the node depends on and does not control works.

The node tracks the health of what it depends on and does not control, its external dependencies
(an ``ExternalDependency``), such as the aMule client; a part is their plain word.
Each part has rules (a ``HealthRule``), such as "aMule does not answer", each with the alert it
sends and its end (a ``HealthAlert``).
At each check, the code records in ``NodeHealth`` whether the rule detected its case.
From its latest checks, the rule says whether the part is healthy or failing (a ``HealthState``).
For example, the status reading asks aMule for its status every minute.
Detected 3 times in a row, the client is failing: "amuled unreachable for 2 min".
Detected fewer than 2 times in the last 10, it is healthy again: "amuled reachable again".
Turning healthy takes longer than failing, so a flaky client does not alert on and off.
Before its first 3 checks, its state is unknown, and nothing is sent.
Each notification sent is checked too: whether its service took it; and each save of the
notifications left: whether the local database took it.
A bug is no outage: the supervisor counts those of each object it rebuilds, never here.
"""
