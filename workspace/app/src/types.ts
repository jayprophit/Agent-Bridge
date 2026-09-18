export type WorkspaceMode = 'chat' | 'code';
export type ThemeId = 'dark' | 'frost' | 'aurora' | 'amber';

export interface ShellStatus {
  model: string;
  agent: string;
  task: string;
  progress: number;
  approval: 'none' | 'pending' | 'approved';
  verification: 'idle' | 'running' | 'passed' | 'failed';
}
