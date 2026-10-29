import { call } from '@/lib/frappe-sdk';

/** One Execution Profile a code step may use, as the server reports it. */
export interface CodeFlowProfile {
  name: string;
  approval_mode: 'Auto Approve' | 'Ask Every Time' | 'Never Allow';
  filesystem_policy?: string;
  max_wall_time_s: number;
  is_builtin?: boolean;
  /** False for disabled, "Never Allow" and "Shared Directory" profiles. */
  usable: boolean;
  reason?: string;
}

/** Whether Execute code may be used in Flows right now, and by this user (huf.ai.flow.code_node.get_code_flow_status). */
export interface CodeFlowStatus {
  /** Site configuration kill switch (huf_python_execution_enabled). */
  server_switch: boolean;
  /** Agent Settings: "Allow code execution in Flows". */
  allowed: boolean;
  /** Both of the above are on. */
  enabled: boolean;
  /** The signed-in user holds flows.execute_code. */
  can_execute: boolean;
  /** The signed-in user is a System Manager and may flip the setting. */
  can_manage: boolean;
  /** enabled && can_execute: the Execute code card is offered. */
  available: boolean;
  max_code_bytes: number;
  default_profile: string;
  default_timeout_s: number;
  profiles: CodeFlowProfile[];
}

export async function fetchCodeFlowStatus(): Promise<CodeFlowStatus> {
  const result = await call.get('huf.ai.flow.code_node.get_code_flow_status');
  return result.message as CodeFlowStatus;
}
