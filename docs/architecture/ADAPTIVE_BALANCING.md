# Adaptive Balancing (v0.8, Part A)

Nine configurable weights (compatibility, benchmark, pressure, latency,
energy, memory, reliability, priority, owner preference). Reliability
outranks speed: a fast unreliable model never beats a slower reliable one.
Pressure responses: cut CPU workers, shift lanes, shrink cache, unload
models, use artifact references. Measured in
V08_RESOURCE_BALANCE_REPORT.json/.md (12 mixed tasks: 0.396s sequential vs
0.096s waves+placement, 0 errors).
