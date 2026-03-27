import { ActionOption } from "../types/modal.types";

export const actionOptions: ActionOption[] = [
  {
    id: "transform",
    name: "Transform Data",
    description: "Transform and map data fields",
    icon: "Repeat",
    category: "transform",
  },
  {
    id: "router",
    name: "Router",
    description: "Split flow into branches with conditions",
    icon: "GitBranch",
    category: "control",
  },
  {
    id: "loop",
    name: "Loop",
    description: "Iterate over array data",
    icon: "RotateCw",
    category: "control",
  },
  {
    id: "human-in-loop",
    name: "Human in Loop",
    description: "Request human approval",
    icon: "UserCheck",
    category: "control",
  },
  {
    id: "agent-run",
    name: "Run Agent",
    description: "Execute an AI agent",
    icon: "Bot",
    category: "control",
  },
  {
    id: "tool-call",
    name: "Call Tool",
    description: "Execute a tool function",
    icon: "Wrench",
    category: "control",
  },
  {
    id: "condition",
    name: "Condition",
    description: "Branch based on condition",
    icon: "GitCommitHorizontal",
    category: "control",
  },
  {
    id: "http-request",
    name: "HTTP Request",
    description: "Make HTTP API calls",
    icon: "Globe",
    category: "utility",
  },
];
