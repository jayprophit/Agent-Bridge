# Model Benchmark Results (v0.7)

## Summary
- **Benchmark Schema Version**: 1.0.0
- **Benchmark Suite Version**: 1.0.0
- **Device**: Windows 10.0.19045, Intel i7-870, 16GB RAM, GTX 1050 Ti 4GB VRAM
- **Provider**: Ollama 0.33.3 (local)
- **Date**: 2026-09-11

## Models Tested


### ollama:hhao/qwen2.5-coder-tools:3b

- **Samples**: 10
- **Confidence**: HIGH
- **Avg Tokens/sec**: 3.4
- **Avg TTFT**: N/Ams
- **Task Success Rate**: 100.0%
- **Tool Call Reliability**: 50.0%
- **Structured Output Reliability**: 50.0%
- **Error Rate**: N/A
- **Peak RAM**: 34MB
- **Peak VRAM**: 3189MB

**Observations**:

- CONTEXT_TEST/short_context: cold=WARM, tps=4.1, success=True, tool_valid=None, struct_valid=None, load=8ms
- TOOL_CALL/search_and_list: cold=WARM, tps=3.9, success=True, tool_valid=True, struct_valid=None, load=Nonems
- STRUCTURED_OUTPUT/json_person: cold=WARM, tps=4.3, success=True, tool_valid=None, struct_valid=True, load=20ms
- CODE_GENERATION/python_add_function: cold=WARM, tps=3.9, success=True, tool_valid=None, struct_valid=None, load=9ms
- SIMPLE_GENERATION/simple_greeting: cold=COLD, tps=0.7, success=True, tool_valid=None, struct_valid=None, load=37574ms
- CONTEXT_TEST/short_context: cold=WARM, tps=4.1, success=True, tool_valid=None, struct_valid=None, load=10ms
- TOOL_CALL/search_and_list: cold=WARM, tps=4.0, success=True, tool_valid=None, struct_valid=None, load=Nonems
- STRUCTURED_OUTPUT/json_person: cold=WARM, tps=4.3, success=True, tool_valid=None, struct_valid=False, load=9ms
- CODE_GENERATION/python_add_function: cold=WARM, tps=3.9, success=True, tool_valid=None, struct_valid=None, load=8ms
- SIMPLE_GENERATION/simple_greeting: cold=COLD, tps=0.7, success=True, tool_valid=None, struct_valid=None, load=41184ms


### ollama:qwen3.5:2b-q4_K_M

- **Samples**: 1
- **Confidence**: PRELIMINARY
- **Avg Tokens/sec**: N/A
- **Avg TTFT**: N/Ams
- **Task Success Rate**: N/A
- **Tool Call Reliability**: N/A
- **Structured Output Reliability**: N/A
- **Error Rate**: 100.0%
- **Peak RAM**: 34MB
- **Peak VRAM**: 2869MB

**Observations**:

- SIMPLE_GENERATION/simple_greeting: cold=COLD, tps=N/A, success=False, tool_valid=None, struct_valid=None, load=Nonems


### ollama:qwen3:0.6b

- **Samples**: 12
- **Confidence**: HIGH
- **Avg Tokens/sec**: 17.3
- **Avg TTFT**: N/Ams
- **Task Success Rate**: 100.0%
- **Tool Call Reliability**: 100.0%
- **Structured Output Reliability**: 66.7%
- **Error Rate**: N/A
- **Peak RAM**: 34MB
- **Peak VRAM**: 3818MB

**Observations**:

- CONTEXT_TEST/short_context: cold=WARM, tps=17.6, success=True, tool_valid=None, struct_valid=None, load=9ms
- TOOL_CALL/search_and_list: cold=WARM, tps=17.5, success=True, tool_valid=True, struct_valid=None, load=Nonems
- STRUCTURED_OUTPUT/json_person: cold=WARM, tps=17.8, success=True, tool_valid=None, struct_valid=True, load=13ms
- CODE_GENERATION/python_add_function: cold=WARM, tps=17.7, success=True, tool_valid=None, struct_valid=None, load=13ms
- SIMPLE_GENERATION/simple_greeting: cold=COLD, tps=17.6, success=True, tool_valid=None, struct_valid=None, load=8ms
- TOOL_CALL/search_and_list: cold=WARM, tps=17.3, success=True, tool_valid=True, struct_valid=None, load=Nonems
- STRUCTURED_OUTPUT/json_person: cold=WARM, tps=16.8, success=True, tool_valid=None, struct_valid=True, load=15ms
- CONTEXT_TEST/short_context: cold=WARM, tps=17.5, success=True, tool_valid=None, struct_valid=None, load=20ms
- TOOL_CALL/search_and_list: cold=WARM, tps=17.3, success=True, tool_valid=True, struct_valid=None, load=Nonems
- STRUCTURED_OUTPUT/json_person: cold=WARM, tps=17.7, success=True, tool_valid=None, struct_valid=False, load=23ms
- CODE_GENERATION/python_add_function: cold=WARM, tps=17.8, success=True, tool_valid=None, struct_valid=None, load=9ms
- SIMPLE_GENERATION/simple_greeting: cold=COLD, tps=15.2, success=True, tool_valid=None, struct_valid=None, load=10671ms


### ollama:qwen3:1.7b

- **Samples**: 11
- **Confidence**: HIGH
- **Avg Tokens/sec**: 9.4
- **Avg TTFT**: N/Ams
- **Task Success Rate**: 100.0%
- **Tool Call Reliability**: 100.0%
- **Structured Output Reliability**: 66.7%
- **Error Rate**: N/A
- **Peak RAM**: 34MB
- **Peak VRAM**: 3817MB

**Observations**:

- CONTEXT_TEST/short_context: cold=WARM, tps=9.4, success=True, tool_valid=None, struct_valid=None, load=8ms
- TOOL_CALL/search_and_list: cold=WARM, tps=9.4, success=True, tool_valid=True, struct_valid=None, load=Nonems
- STRUCTURED_OUTPUT/json_person: cold=WARM, tps=9.4, success=True, tool_valid=None, struct_valid=True, load=8ms
- CODE_GENERATION/python_add_function: cold=WARM, tps=9.3, success=True, tool_valid=None, struct_valid=None, load=7ms
- SIMPLE_GENERATION/simple_greeting: cold=COLD, tps=9.4, success=True, tool_valid=None, struct_valid=None, load=8ms
- STRUCTURED_OUTPUT/json_person: cold=WARM, tps=9.4, success=True, tool_valid=None, struct_valid=True, load=44801ms
- CONTEXT_TEST/short_context: cold=WARM, tps=9.4, success=True, tool_valid=None, struct_valid=None, load=11ms
- TOOL_CALL/search_and_list: cold=WARM, tps=9.3, success=True, tool_valid=True, struct_valid=None, load=Nonems
- STRUCTURED_OUTPUT/json_person: cold=WARM, tps=9.4, success=True, tool_valid=None, struct_valid=False, load=7ms
- CODE_GENERATION/python_add_function: cold=WARM, tps=9.3, success=True, tool_valid=None, struct_valid=None, load=7ms
- SIMPLE_GENERATION/simple_greeting: cold=COLD, tps=9.4, success=True, tool_valid=None, struct_valid=None, load=21268ms

