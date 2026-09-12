# Workload Placement (v0.8, Part A)

22 workload kinds (MODEL_INFERENCE … BACKGROUND_INDEXING) mapped to 10
resource kinds. Scheduler emits dependency-ordered waves; write collisions
serialize (never concurrent writes to one file). Placement decisions carry
reasons, scores, fallbacks, and benchmark-evidence flags for audit.
