export const doctype = {
  User: "User",
  Role: "Role",
  Agent: "Agent",
  "AI Provider": "AI Provider",
  "AI Model": "AI Model",
  "Agent Tool Function": "Agent Tool Function",
  "Agent Tool Type": "Agent Tool Type",
  "Agent Trigger": "Agent Trigger",
  "Agent Conversation": "Agent Conversation",
  "Agent Message": "Agent Message",
  "Agent Run": "Agent Run",
  "Agent Prompt": "Agent Prompt",
  "Agent Prompt Category": "Agent Prompt Category",
  "MCP Server": "MCP Server",
  "Flow Definition": "Flow Definition",
  "Flow Run": "Flow Run",
  "Knowledge Source": "Knowledge Source",
  "Knowledge Input": "Knowledge Input",
  "Huf Data Table": "Huf Data Table",
} as const;

export type DocType = typeof doctype[keyof typeof doctype];
