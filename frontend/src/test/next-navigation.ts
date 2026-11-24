import { vi } from "vitest";

export const router = { replace: vi.fn(), push: vi.fn(), back: vi.fn() };
let pathname = "/";

export function setPathname(value: string): void {
  pathname = value;
}

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => pathname,
  useParams: () => ({}),
}));
