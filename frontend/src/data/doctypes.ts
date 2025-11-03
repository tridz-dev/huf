export const doctype = {
  User: "User",
  Agent: "Agent",
  "AI Provider": "AI Provider",
  "AI Model": "AI Model",
} as const;

export type DocType = typeof doctype[keyof typeof doctype];
