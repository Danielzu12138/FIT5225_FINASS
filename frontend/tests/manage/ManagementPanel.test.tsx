import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthContext, type AuthContextValue } from "../../src/auth/AuthContext";
import {
  ManagementPanel,
  type ManagementClient,
  type ManagementResult,
} from "../../src/manage/ManagementPanel";


const RESULT: ManagementResult = {
  media_id: "22222222-2222-4222-8222-222222222222",
  media_type: "image",
  original_url: "https://downloads.example.test/originals/a/camera.jpg",
  thumbnail_url: "https://downloads.example.test/derived/a/thumbnail.jpg",
  tag_counts: { dingo: 2 },
};


afterEach(cleanup);


function authValue(): AuthContextValue {
  return {
    status: "authenticated",
    config: null,
    accessToken: "access-token",
    login: vi.fn(),
    signup: vi.fn(),
    localLogin: vi.fn(),
    completeCallback: vi.fn(),
    logout: vi.fn(),
  };
}


function client(overrides: Partial<ManagementClient> = {}): ManagementClient {
  return {
    queryByFile: vi.fn().mockResolvedValue([RESULT]),
    updateTags: vi.fn().mockResolvedValue(undefined),
    deleteMedia: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}


function renderPanel(api: ManagementClient) {
  render(
    <AuthContext.Provider value={authValue()}>
      <ManagementPanel client={api} />
    </AuthContext.Provider>,
  );
}


async function query(api: ManagementClient) {
  renderPanel(api);
  const file = new File(["image"], "query.jpg", { type: "image/jpeg" });
  fireEvent.change(screen.getByLabelText("Query file"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "Find matching media" }));
  await screen.findByRole("checkbox", { name: "Select camera.jpg" });
}


describe("ManagementPanel", () => {
  it("queries with the shared auth token and renders selectable results", async () => {
    const api = client();
    await query(api);

    expect(api.queryByFile).toHaveBeenCalledWith(expect.any(File), "access-token");
    expect(screen.getByRole("link", { name: "Open camera.jpg" })).toHaveAttribute(
      "href",
      RESULT.original_url,
    );
    expect(screen.getByText("dingo: 2")).toBeInTheDocument();
    expect(screen.getByText("0 of 1 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Select all" }));
    expect(screen.getByText("1 of 1 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(screen.getByText("0 of 1 selected")).toBeInTheDocument();
  });

  it("shows accessible empty and error states", async () => {
    const emptyApi = client({ queryByFile: vi.fn().mockResolvedValue([]) });
    renderPanel(emptyApi);
    const file = new File(["image"], "query.jpg", { type: "image/jpeg" });
    fireEvent.change(screen.getByLabelText("Query file"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Find matching media" }));
    expect(await screen.findByText("No matching media found.")).toBeInTheDocument();

    cleanup();
    const failingApi = client({ queryByFile: vi.fn().mockRejectedValue(new Error("offline")) });
    renderPanel(failingApi);
    fireEvent.change(screen.getByLabelText("Query file"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Find matching media" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("offline");
  });

  it("updates selected results with normalized tags", async () => {
    const api = client();
    await query(api);
    fireEvent.click(screen.getByRole("checkbox", { name: "Select camera.jpg" }));
    fireEvent.change(screen.getByLabelText("Tags"), { target: { value: " Dingo, night, dingo " } });
    fireEvent.click(screen.getByRole("button", { name: "Add tags" }));

    await waitFor(() =>
      expect(api.updateTags).toHaveBeenCalledWith(
        [RESULT.original_url],
        ["dingo", "night"],
        1,
        "access-token",
      ),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Tags updated.");
  });

  it("requires confirmation before deleting selected results", async () => {
    const api = client();
    await query(api);
    fireEvent.click(screen.getByRole("checkbox", { name: "Select camera.jpg" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));

    expect(screen.getByRole("dialog", { name: "Confirm deletion" })).toBeInTheDocument();
    expect(api.deleteMedia).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));

    await waitFor(() =>
      expect(api.deleteMedia).toHaveBeenCalledWith([RESULT.original_url], "access-token"),
    );
    expect(screen.getByText("No matching media found.")).toBeInTheDocument();
  });
});
