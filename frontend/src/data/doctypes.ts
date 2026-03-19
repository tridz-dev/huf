export const doctype = {
  User: "User",
  Agent: "Agent",
  "AI Provider": "AI Provider",
  "AI Model": "AI Model",
  "Agent Tool Function": "Agent Tool Function",
  "Agent Tool Type": "Agent Tool Type",
  "Agent Trigger": "Agent Trigger",
  "Agent Conversation": "Agent Conversation",
  "Agent Message": "Agent Message",
  "Agent Run": "Agent Run",
  "MCP Server": "MCP Server",
  "Huf Data Table": "Huf Data Table",
  "Knowledge Source": "Knowledge Source",
} as const;

export type DocType = typeof doctype[keyof typeof doctype];
