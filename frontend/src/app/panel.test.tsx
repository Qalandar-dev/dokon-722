import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { router } from "@/test/next-navigation";
import { jsonResponse, renderWithQuery } from "@/test/utils";
import { AuthProvider } from "@/lib/auth";
import { setAccessToken } from "@/lib/api-client";

import PanelLayout from "./(panel)/layout";
import LoginPage from "./login/page";

const admin = (permissions: string[]) => ({
  id: "a1",
  email: "op@store.uz",
  full_name: "Operator Ali",
  role: "operator",
  role_title: "Operator",
  permissions,
});

function mockApi(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) =>
    handler(String(input), init),
  );
}

beforeEach(() => {
  router.replace.mockClear();
  setAccessToken(null);
});

describe("protected panel", () => {
  it("redirects to /login when there is no session", async () => {
    mockApi(() => jsonResponse({ error: { code: "invalid_refresh", message: "x" } }, 401));
    renderWithQuery(
      <AuthProvider>
        <PanelLayout>
          <p>Maxfiy</p>
        </PanelLayout>
      </AuthProvider>,
    );
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("Maxfiy")).not.toBeInTheDocument();
  });

  it("shows only the menu items the admin may use", async () => {
    mockApi(() =>
      jsonResponse({
        access_token: "t",
        expires_at: "",
        admin: admin(["orders.view", "products.view"]),
      }),
    );
    renderWithQuery(
      <AuthProvider>
        <PanelLayout>
          <p>Ichki sahifa</p>
        </PanelLayout>
      </AuthProvider>,
    );
    expect(await screen.findByText("Ichki sahifa")).toBeInTheDocument();
    const nav = screen.getAllByRole("navigation", { name: "Asosiy menyu" })[0]!;
    expect(nav).toHaveTextContent("Buyurtmalar");
    expect(nav).toHaveTextContent("Mahsulotlar");
    expect(nav).not.toHaveTextContent("Xodimlar");
    expect(nav).not.toHaveTextContent("Sozlamalar");
    expect(screen.getByText("Operator Ali")).toBeInTheDocument();
  });
});

describe("login form", () => {
  it("validates input before calling the API", async () => {
    mockApi(() => jsonResponse({ error: { code: "invalid_refresh", message: "x" } }, 401));
    renderWithQuery(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: /Kirish/ }));
    expect(await screen.findByText("Email kiriting")).toBeInTheDocument();
    expect(screen.getByText("Parol kiriting")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Email"), "notogri");
    await userEvent.click(screen.getByRole("button", { name: /Kirish/ }));
    expect(await screen.findByText("Email noto‘g‘ri")).toBeInTheDocument();
  });

  it("shows the server's message on wrong credentials and signs in on success", async () => {
    let attempts = 0;
    mockApi((url) => {
      if (url.endsWith("/refresh"))
        return jsonResponse({ error: { code: "invalid_refresh", message: "x" } }, 401);
      attempts += 1;
      return attempts === 1
        ? jsonResponse(
            { error: { code: "invalid_credentials", message: "Email yoki parol noto‘g‘ri." } },
            401,
          )
        : jsonResponse({ access_token: "t", expires_at: "", admin: admin(["orders.view"]) });
    });
    renderWithQuery(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );
    await userEvent.type(await screen.findByLabelText("Email"), "op@store.uz");
    await userEvent.type(screen.getByLabelText("Parol"), "notogri-parol");
    await userEvent.click(screen.getByRole("button", { name: /Kirish/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Email yoki parol noto‘g‘ri.");

    await userEvent.click(screen.getByRole("button", { name: /Kirish/ }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
  });
});
