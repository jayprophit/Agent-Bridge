# Voice Agent (v0.8, Part D)

`voice/` pipeline: microphone -> input -> [VAD] -> STT -> DefaultAgent ->
tools -> text -> TTS -> speaker -> avatar events, all on the shared
EventBus with the SAME agent session as Chat/Work. Push-to-talk and
conversation modes; stop/mute/interrupt; device selection; explicit
recording consent (never silent). No audio capture backend installed:
microphone is presence-only; fixtures drive tests.
