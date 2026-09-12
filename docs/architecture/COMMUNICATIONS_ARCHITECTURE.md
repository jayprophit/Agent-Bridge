# Communications Architecture (v0.8, Parts E-F)

One `comms/` core, provider-neutral throughout. Email: local drafts as
artifacts (low risk); send/read/search need a configured provider and
owner approval; no credentials in the tree (asserted by test). Telephony:
CallProvider interface (SIP/WebRTC/Twilio-style/PSTN adapters plug in);
LoopbackCallProvider proves the lifecycle with zero PSTN claims. Default
MANUAL_ANSWER; recording/transcription require explicit consent, never
silent. See EMAIL_TOOLS.md, TELEPHONY_AGENT.md.
