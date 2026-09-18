type TaskStatus = 'PENDING' | 'RUNNING' | 'WAITING_APPROVAL' | 'FAILED' | 'VERIFIED_COMPLETE';

type TaskStatusLabel = {
  PENDING: 'Pending',
  RUNNING: 'Running',
  WAITING_APPROVAL: 'Waiting for Approval',
  FAILED: 'Failed',
  VERIFIED_COMPLETE: 'Verified Complete'
};

function getStatusLabel(status: TaskStatus): TaskStatusLabel[TaskStatus] {
  return TaskStatusLabel[status];
}

function isTerminalStatus(status: TaskStatus): boolean {
  return status === 'FAILED' || status === 'VERIFIED_COMPLETE';
}
