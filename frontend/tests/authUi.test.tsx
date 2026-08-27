import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthContext, type AuthContextValue } from "../src/auth/AuthContext";
import { ProtectedRoute } from "../src/auth/ProtectedRoute";
import { CallbackPage } from "../src/pages/CallbackPage";
import { LoginPage } from "../src/pages/LoginPage";
import { VerificationPage } from "../src/pages/VerificationPage";

afterEach(cleanup);

function value(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    status: "anonymous",
    config: {
      region: "ap-southeast-2",
      user_pool_id: "pool",
      app_client_id: "client",
      oauth_domain: "https://example.test",
      redirect_uri: "http://localhost/auth/callback",
      external_providers: ["Google"],
    },
    accessToken: null,
    login: vi.fn(),
    signup: vi.fn(),
    localLogin: vi.fn(),
    completeCallback: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  };
}

describe("authentication UI", () => {
  it("redirects anonymous visitors away from protected content", () => {
    render(
      <AuthContext.Provider value={value()}>
        <MemoryRouter initialEntries={["/library"]}>
          <Routes>
            <Route path="/login" element={<p>Sign in required</p>} />
            <Route element={<ProtectedRoute />}>
              <Route path="/library" element={<p>Private library</p>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    );

    expect(screen.getByText("Sign in required")).toBeInTheDocument();
    expect(screen.queryByText("Private library")).not.toBeInTheDocument();
  });

  it("renders protected content for an authenticated visitor", () => {
    render(
      <AuthContext.Provider value={value({ status: "authenticated", accessToken: "token" })}>
        <MemoryRouter initialEntries={["/library"]}>
          <Routes>
            <Route element={<ProtectedRoute />}>
              <Route path="/library" element={<p>Private library</p>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    );

    expect(screen.getByText("Private library")).toBeInTheDocument();
  });

  it("shows only externally configured identity providers", () => {
    render(
      <AuthContext.Provider value={value()}>
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      </AuthContext.Provider>,
    );

    expect(screen.getByRole("button", { name: "Continue with Google" })).toBeInTheDocument();
    expect(screen.getByText("Field research, organised.")).toBeInTheDocument();
    expect(screen.getByText("A secure home for wildlife observations from capture to discovery.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue with Microsoft" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Use local demo account" })).not.toBeInTheDocument();
  });

  it("shows local login only when the backend explicitly enables it", () => {
    const localValue = value({
      config: {
        region: "ap-southeast-2",
        user_pool_id: "local",
        app_client_id: "local",
        oauth_domain: "https://local.invalid",
        redirect_uri: "http://localhost/auth/callback",
        external_providers: [],
        local_auth_enabled: true,
      },
    });
    render(
      <AuthContext.Provider value={localValue}>
        <MemoryRouter><LoginPage /></MemoryRouter>
      </AuthContext.Provider>,
    );
    expect(screen.getByRole("button", { name: "Use local demo account" })).toBeInTheDocument();
  });

  it("redirects to the library after authentication completes", async () => {
    render(
      <AuthContext.Provider value={value({ status: "authenticated", accessToken: "token" })}>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/library" element={<p data-testid="library-route">Private library</p>} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    );

    expect(await screen.findByTestId("library-route")).toBeInTheDocument();
  });

  it("uses the archive identity on verification and callback screens", () => {
    const pending = value({ config: null });
    const { unmount } = render(
      <AuthContext.Provider value={pending}>
        <MemoryRouter><VerificationPage /></MemoryRouter>
      </AuthContext.Provider>,
    );
    expect(screen.getByText("Email verification")).toBeInTheDocument();
    expect(screen.getByText("Pacific BioArchive")).toBeInTheDocument();
    unmount();

    render(
      <AuthContext.Provider value={pending}>
        <MemoryRouter><CallbackPage /></MemoryRouter>
      </AuthContext.Provider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Validating your secure session");
    expect(screen.getByText("Pacific BioArchive")).toBeInTheDocument();
  });
});
