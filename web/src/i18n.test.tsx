import { describe, expect, it } from "vitest";
import { DICT } from "./i18n";

const sourceFiles = import.meta.glob(
  ["./App.tsx", "./ui.tsx", "./pages/*.tsx", "./components/*.tsx"],
  { query: "?raw", import: "default", eager: true },
) as Record<string, string>;

describe("TH/EN contract", () => {
  it("has non-empty Thai and English values for every translation key", () => {
    for (const [key, value] of Object.entries(DICT)) {
      expect(value.th.trim(), key + " Thai translation").not.toBe("");
      expect(value.en.trim(), key + " English translation").not.toBe("");
    }
  });

  it("defines every static translation key used by the application", () => {
    const missing = new Set<string>();
    for (const source of Object.values(sourceFiles)) {
      for (const match of source.matchAll(/\bt\("([^"]+)"\)/g)) {
        if (!DICT[match[1]]) missing.add(match[1]);
      }
    }
    expect([...missing].sort()).toEqual([]);
  });

  it("keeps every route-level page connected to the language context", () => {
    const missing = Object.entries(sourceFiles)
      .filter(([path]) => path.includes("/pages/"))
      .filter(([, source]) => !source.includes("useLang"))
      .map(([path]) => path)
      .sort();
    expect(missing).toEqual([]);
  });
});
