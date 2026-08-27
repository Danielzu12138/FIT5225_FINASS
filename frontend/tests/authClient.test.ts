import { afterEach, describe, expect, it, vi } from "vitest";

import { BrowserAuthClient, buildAuthorizeUrl, buildLogoutUrl, buildSignupUrl, validateCallback } from "../src/auth/authClient";

const config = {
  region: "ap-southeast-2",
  user_pool_id: "ap-southeast-2_example",
  app_client_id: "client-id",
  oauth_domain: "https://example.auth.ap-southeast-2.amazoncognito.com",
  redirect_uri: "http://localhost:5173/auth/callback",
  external_providers: ["Google", "Microsoft"],
};

describe("Cognito hosted UI PKCE", () => {
  afterEach(() => {
    sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it("builds an authorization-code URL with PKCE and optional provider", () => {
    const url = new URL(buildAuthorizeUrl(config, "state-123", "challenge-456", "Google"));

    expect(url.pathname).toBe("/oauth2/authorize");
    expect(url.searchParams.get("response_type")).toBe("code");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("identity_provider")).toBe("Google");
    expect(url.searchParams.get("state")).toBe("state-123");
  });

  it("accepts a matching callback and rejects state mismatch", () => {
    expect(validateCallback("?code=abc&state=expected", "expected")).toEqual({ code: "abc" });
    expect(() => validateCallback("?code=abc&state=wrong", "expected")).toThrow("state");
  });

  it("builds a Cognito registration entry point", () => {
    const url = new URL(buildSignupUrl(config, "state", "challenge"));
    expect(url.pathname).toBe("/signup");
    expect(url.searchParams.get("response_type")).toBe("code");
  });

  it("uses the configured browser origin for Cognito logout", () => {
    const url = new URL(buildLogoutUrl(config));

    expect(url.pathname).toBe("/logout");
    expect(url.searchParams.get("client_id")).toBe("client-id");
    expect(url.searchParams.get("logout_uri")).toBe("http://localhost:5173");
  });

  it("refreshes an expired access token without exposing the refresh token", async () => {
    sessionStorage.setItem("pba.oauth.state", "expected");
    sessionStorage.setItem("pba.oauth.verifier", "verifier");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          access_token: "expired-access",
          refresh_token: "refresh-only-in-storage",
          expires_in: -1,
          token_type: "Bearer",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ access_token: "fresh-access", expires_in: 3600, token_type: "Bearer" }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const client = new BrowserAuthClient(config, sessionStorage);

    await client.completeCallback("?code=abc&state=expected");
    expect(await client.restoreSession()).toBe("fresh-access");

    const refreshRequest = fetchMock.mock.calls[1][1] as RequestInit;
    expect(refreshRequest.body?.toString()).toContain("grant_type=refresh_token");
    expect(refreshRequest.body?.toString()).toContain("refresh_token=refresh-only-in-storage");
  });
});
