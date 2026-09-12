# Telephony Agent (v0.8, Part F)

DefaultAgent-compatible call lifecycle: incoming -> answer policy ->
STT fixture -> agent -> TTS fixture -> caller -> hangup -> transcript
artifact. Policies: MANUAL_ANSWER (default), AUTO_ANSWER_TRUSTED,
AUTO_ANSWER_ALL, BUSINESS_HOURS, DO_NOT_DISTURB. DTMF, duration,
escalation included. Real PSTN correctly remains PROVIDER_REQUIRED.
