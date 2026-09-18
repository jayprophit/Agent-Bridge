export interface AIModelOption {
  id: string;
  name: string;
  badge: string;
  provider: 'Google' | 'Anthropic' | 'OpenAI' | 'Aetherius';
  description: string;
  contextWindow: string;
  speed: 'Ultra Fast' | 'Fast' | 'Deep Reasoning' | 'Autonomous';
  recommendedFor: string;
  color: string;
}

export const AVAILABLE_MODELS: AIModelOption[] = [
  {
    id: 'gemini-2.5-pro',
    name: 'Gemini 2.5 Pro',
    badge: 'Pro Reasoning',
    provider: 'Google',
    description: 'Deep analytical reasoning, multi-file code architecture, and high precision',
    contextWindow: '2M tokens',
    speed: 'Deep Reasoning',
    recommendedFor: 'Complex refactoring & architecture',
    color: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30',
  },
  {
    id: 'gemini-2.5-flash',
    name: 'Gemini 2.5 Flash',
    badge: 'Ultra Fast',
    provider: 'Google',
    description: 'Sub-second latency, multimodal reasoning, and rapid iterative edits',
    contextWindow: '1M tokens',
    speed: 'Ultra Fast',
    recommendedFor: 'Quick edits, unit tests & chat',
    color: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
  },
  {
    id: 'gemini-2.0-flash-thinking',
    name: 'Gemini 2.0 Flash Thinking',
    badge: 'Thinking Engine',
    provider: 'Google',
    description: 'Visible chain-of-thought logic steps for tricky algorithmic challenges',
    contextWindow: '1M tokens',
    speed: 'Fast',
    recommendedFor: 'Complex debugging & logic verification',
    color: 'text-indigo-400 bg-indigo-500/10 border-indigo-500/30',
  },
  {
    id: 'claude-3.7-sonnet',
    name: 'Claude 3.7 Sonnet',
    badge: 'Hybrid Reasoning',
    provider: 'Anthropic',
    description: 'Dynamic reasoning model tailored for full-stack autonomous coding',
    contextWindow: '200k tokens',
    speed: 'Fast',
    recommendedFor: 'Frontend design & nuanced writing',
    color: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  },
  {
    id: 'antigravity-agent-v4',
    name: 'Antigravity Agent v4',
    badge: 'Autonomous',
    provider: 'Aetherius',
    description: 'Autonomous multi-file orchestration and workspace tool execution',
    contextWindow: '1M tokens',
    speed: 'Autonomous',
    recommendedFor: 'End-to-end task delegation',
    color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  },
];
