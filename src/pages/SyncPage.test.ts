import { describe, expect, it } from "vitest";
import { formatBytes, formatCountdown } from "./SyncPage";

describe("formatBytes", () => {
  it("formats device capacity in gigabytes", () => {
    expect(formatBytes(38.2 * 1024 ** 3)).toBe("38.2 GB");
  });

  it("formats a live scheduler deadline", () => {
    expect(formatCountdown(700, 100)).toBe("10m 00s");
    expect(formatCountdown(99, 100)).toBe("0m 00s");
  });
});
