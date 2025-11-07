export const doctype = {
  User: "User",
  Agent: "Agent",
  "AI Provider": "AI Provider",
  "AI Model": "AI Model",
  "Agent Tool Function": "Agent Tool Function",
  "Agent Tool Type": "Agent Tool Type",
  "Agent Trigger": "Agent Trigger",
} as const;

export type DocType = typeof doctype[keyof typeof doctype];
