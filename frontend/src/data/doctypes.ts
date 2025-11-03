export const doctype = {
  User: "User",
  Agent: "Agent",
} as const;

export type DocType = typeof doctype[keyof typeof doctype];
