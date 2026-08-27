import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { AuthContext, type AuthContextValue } from "../../src/auth/AuthContext";
import { MediaGallery } from "../../src/library/MediaGallery";

const authenticated: AuthContextValue = {
  status: "authenticated",
  config: null,
  accessToken: "access-token",
  login: vi.fn(),
  signup: vi.fn(),
  localLogin: vi.fn(),
  completeCallback: vi.fn(),
  logout: vi.fn(),
};

afterEach(cleanup);

test("renders image thumbnail links and video poster cards from signed media results", async () => {
  const list = vi.fn().mockResolvedValue({
    results: [
      {
        media_id: "image-1",
        media_type: "image",
        status: "ready",
        original_url: "https://downloads.example.test/originals/camera.jpg",
        thumbnail_url: "https://downloads.example.test/derived/camera.jpg",
        tag_counts: { dingo: 2 },
      },
      {
        media_id: "video-1",
        media_type: "video",
        status: "prepared",
        original_url: "https://downloads.example.test/originals/clip.mp4",
        thumbnail_url: "https://downloads.example.test/derived/clip.jpg",
        tag_counts: { wombat: 1 },
      },
      {
        media_id: "processing-1",
        media_type: "image",
        status: "processing",
        original_url: null,
        thumbnail_url: null,
        tag_counts: {},
      },
    ],
  });

  render(
    <AuthContext.Provider value={authenticated}>
      <MediaGallery client={{ list }} />
    </AuthContext.Provider>,
  );

  expect(screen.getByRole("status")).toHaveTextContent("Loading media");
  expect(await screen.findByAltText("Image media thumbnail")).toHaveAttribute(
    "src",
    "https://downloads.example.test/derived/camera.jpg",
  );
  expect(screen.getByRole("link", { name: "Open image original" })).toHaveAttribute(
    "href",
    "https://downloads.example.test/originals/camera.jpg",
  );
  expect(screen.getByLabelText("Video media preview")).toHaveAttribute(
    "poster",
    "https://downloads.example.test/derived/clip.jpg",
  );
  expect(screen.getByRole("link", { name: "Open video original" })).toHaveAttribute(
    "href",
    "https://downloads.example.test/originals/clip.mp4",
  );
  expect(screen.getByText("Processing")).toBeInTheDocument();
  expect(screen.getByText("dingo × 2")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "All 3" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Videos 1" }));
  expect(screen.queryByAltText("Image media thumbnail")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Video media preview")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Refresh library" }));
  await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  expect(screen.queryByRole("link", { name: "Open image original processing-1" })).not.toBeInTheDocument();
  expect(list).toHaveBeenLastCalledWith("access-token");
});
