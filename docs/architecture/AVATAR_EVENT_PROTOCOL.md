# Avatar Event Protocol (v0.8, Part G)

Stable events: IDLE, LISTENING, THINKING, SPEAKING, TOOL_RUNNING, SUCCESS,
WARNING, ERROR, EMOTION, GESTURE, VISEME, GAZE, HEAD_MOVEMENT,
BODY_ANIMATION. Presentation MALE/FEMALE/NEUTRAL/CUSTOM is explicit config
(never pitch-derived). Expressions: neutral/happy/concerned/thinking/
surprised/confident — no theatrical animation. Lip sync: provider viseme
timestamps preferred; phoneme map, then amplitude jaw fallback
(15-viseme jaw table in `avatar/protocol.py`).
