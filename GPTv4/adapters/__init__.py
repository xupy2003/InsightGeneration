"""What ties the engine to one task family and one solver: the problem loader (problems.py: ICPC WF and
AtCoder, through ReasoningGraph's loader so the statement is the one the graph builder and the solver saw)
and the solver harness (solver_agentv3.py: Slurm jobs of Solver/agentv3). The engine core (profile,
diagnose, write, compose, loop) reads only what these return."""
