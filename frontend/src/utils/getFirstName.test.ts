import { describe, expect, it } from "vitest";
import { getFirstName } from "./getFirstName";

describe("getFirstName", () => {
  it("returns the first word of a full name", () => {
    expect(getFirstName("Ahmed Khan")).toBe("Ahmed");
  });

  it("returns the whole value for a single name", () => {
    expect(getFirstName("Ahmed")).toBe("Ahmed");
  });

  it("trims surrounding whitespace", () => {
    expect(getFirstName("  Sara Ali  ")).toBe("Sara");
  });

  it("returns empty string for email-like names", () => {
    expect(getFirstName("ahmed@example.com")).toBe("");
  });

  it("returns empty string for missing or blank values", () => {
    expect(getFirstName(undefined)).toBe("");
    expect(getFirstName(null)).toBe("");
    expect(getFirstName("")).toBe("");
    expect(getFirstName("   ")).toBe("");
  });
});
