import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { AuthContext, type AuthContextValue } from "../../src/auth/AuthContext";
import { UploadPanel, type UploadClient } from "../../src/upload/UploadPanel";

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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mediaFile(name: string, type = "image/jpeg"): File {
  const file = new File(["camera-bytes"], name, { type });
  Object.assign(file, { arrayBuffer: () => Promise.resolve(new TextEncoder().encode("camera-bytes").buffer) });
  return file;
}

test("hashes a selected image, reserves it, PUTs it, and refreshes the library", async () => {
  const reserve = vi.fn().mockResolvedValue({
    media_id: "11111111-1111-4111-8111-111111111111",
    duplicate: false,
    status: "reserved",
    upload_url: "https://uploads.example.test/originals/hash/camera.jpg",
    object_key: "originals/hash/camera.jpg",
    expires_in_seconds: 900,
    upload_headers: {
      "Content-Type": "image/jpeg",
      "x-amz-meta-sha256": "ab".repeat(32),
    },
  });
  const directPut = vi.fn().mockResolvedValue({ ok: true });
  const refreshLibrary = vi.fn().mockResolvedValue(undefined);
  const client = { reserve } as UploadClient;
  const digest = vi.fn().mockResolvedValue(new Uint8Array(32).fill(0xab).buffer);
  vi.stubGlobal("crypto", { subtle: { digest } });
  vi.stubGlobal("fetch", directPut);

  render(
    <AuthContext.Provider value={authenticated}>
      <UploadPanel client={client} refreshLibrary={refreshLibrary} />
    </AuthContext.Provider>,
  );
  const file = mediaFile("Camera.JPG", "video/mp4");
  fireEvent.change(screen.getByLabelText("Choose media file"), { target: { files: [file] } });
  expect(screen.getByText("Camera.JPG")).toBeInTheDocument();
  expect(screen.getByText("12 B · Image")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Upload" }));

  await waitFor(() => expect(reserve).toHaveBeenCalledOnce());
  expect(reserve).toHaveBeenCalledWith(
    {
      file_name: "Camera.JPG",
      media_type: "image",
      size_bytes: file.size,
      sha256: "ab".repeat(32),
    },
    "access-token",
  );
  expect(directPut).toHaveBeenCalledWith("https://uploads.example.test/originals/hash/camera.jpg", {
    method: "PUT",
    headers: {
      "Content-Type": "image/jpeg",
      "x-amz-meta-sha256": "ab".repeat(32),
    },
    body: file,
  });
  expect(refreshLibrary).toHaveBeenCalledOnce();
  expect(screen.getByText("Upload complete.")).toBeInTheDocument();
  expect(screen.queryByText("Camera.JPG")).not.toBeInTheDocument();
});

test("reports a duplicate without PUTting the file and still refreshes the library", async () => {
  const reserve = vi.fn().mockResolvedValue({
    media_id: "11111111-1111-4111-8111-111111111111",
    duplicate: true,
    status: "ready",
    upload_url: null,
    object_key: null,
    expires_in_seconds: null,
    upload_headers: null,
  });
  const directPut = vi.fn().mockResolvedValue({ ok: true });
  const refreshLibrary = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("crypto", { subtle: { digest: vi.fn().mockResolvedValue(new ArrayBuffer(32)) } });
  vi.stubGlobal("fetch", directPut);

  render(
    <AuthContext.Provider value={authenticated}>
      <UploadPanel client={{ reserve } as UploadClient} refreshLibrary={refreshLibrary} />
    </AuthContext.Provider>,
  );
  const file = mediaFile("camera.jpg");
  fireEvent.change(screen.getByLabelText("Choose media file"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "Upload" }));

  expect(await screen.findByText("This file is already in your library.")).toBeInTheDocument();
  expect(directPut).not.toHaveBeenCalled();
  expect(refreshLibrary).toHaveBeenCalledOnce();
});

test("uses the canonical reservation headers when the browser MIME type is empty", async () => {
  const reserve = vi.fn().mockResolvedValue({
    media_id: "22222222-2222-4222-8222-222222222222",
    duplicate: false,
    status: "reserved",
    upload_url: "https://uploads.example.test/originals/hash/clip.mp4",
    object_key: "originals/hash/clip.mp4",
    expires_in_seconds: 900,
    upload_headers: {
      "Content-Type": "video/mp4",
      "x-amz-meta-sha256": "ab".repeat(32),
    },
  });
  const directPut = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("crypto", { subtle: { digest: vi.fn().mockResolvedValue(new Uint8Array(32).fill(0xab).buffer) } });
  vi.stubGlobal("fetch", directPut);
  render(
    <AuthContext.Provider value={authenticated}>
      <UploadPanel client={{ reserve } as UploadClient} refreshLibrary={vi.fn().mockResolvedValue(undefined)} />
    </AuthContext.Provider>,
  );
  const file = mediaFile("clip.mp4", "");
  fireEvent.change(screen.getByLabelText("Choose media file"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "Upload" }));

  await waitFor(() => expect(reserve).toHaveBeenCalledOnce());
  expect(reserve.mock.calls[0][0].media_type).toBe("video");
  expect(directPut).toHaveBeenCalledWith(
    "https://uploads.example.test/originals/hash/clip.mp4",
    expect.objectContaining({
      headers: {
        "Content-Type": "video/mp4",
        "x-amz-meta-sha256": "ab".repeat(32),
      },
    }),
  );
});
