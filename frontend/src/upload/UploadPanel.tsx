import { useRef, useState, type FormEvent } from "react";

import { useAuth } from "../auth/AuthContext";

export interface UploadReservationRequest {
  file_name: string;
  media_type: "image" | "video";
  size_bytes: number;
  sha256: string;
}

export interface UploadReservationResponse {
  media_id: string;
  duplicate: boolean;
  status: string;
  upload_url: string | null;
  object_key: string | null;
  expires_in_seconds: number | null;
  upload_headers: Record<string, string> | null;
}

export interface UploadClient {
  reserve(request: UploadReservationRequest, accessToken: string): Promise<UploadReservationResponse>;
}

async function sha256For(file: File): Promise<string> {
  const bytes = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

function mediaTypeFor(file: File): "image" | "video" | null {
  const extension = file.name.toLocaleLowerCase().match(/\.[^.]+$/)?.[0];
  if (extension === ".jpg" || extension === ".jpeg" || extension === ".png") return "image";
  if (extension === ".mp4" || extension === ".mov") return "video";
  return null;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadPanel({
  client,
  refreshLibrary,
}: {
  client: UploadClient;
  refreshLibrary(): Promise<void>;
}) {
  const auth = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  function clearSelection() {
    setFile(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!auth.accessToken) {
      setError("Sign in before uploading media.");
      return;
    }
    if (!file) {
      setError("Choose a media file first.");
      return;
    }
    const mediaType = mediaTypeFor(file);
    if (!mediaType) {
      setError("Choose an image or video file.");
      return;
    }

    setUploading(true);
    setError(null);
    setMessage(null);
    try {
      const reservation = await client.reserve(
        {
          file_name: file.name,
          media_type: mediaType,
          size_bytes: file.size,
          sha256: await sha256For(file),
        },
        auth.accessToken,
      );
      if (reservation.duplicate) {
        await refreshLibrary();
        setMessage("This file is already in your library.");
        clearSelection();
        return;
      }
      if (!reservation.upload_url || !reservation.upload_headers) {
        throw new Error("Upload reservation did not include its signed transport contract.");
      }
      const upload = await fetch(reservation.upload_url, {
        method: "PUT",
        headers: reservation.upload_headers,
        body: file,
      });
      if (!upload.ok) {
        throw new Error("Direct upload failed.");
      }
      await refreshLibrary();
      setMessage("Upload complete.");
      clearSelection();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <section aria-labelledby="upload-heading">
      <div className="panel-heading">
        <div>
          <p className="panel-kicker">New observation</p>
          <h2 id="upload-heading">Upload wildlife media</h2>
        </div>
        <span className="panel-number" aria-hidden="true">01</span>
      </div>
      <p className="panel-description">Add field images or video. The archive creates a lightweight preview and prepares species tags after upload.</p>
      <form className="upload-form" onSubmit={submit}>
        <label className="file-picker">
          <span className="file-picker-title">Choose media file</span>
          <span className="file-picker-help">JPG, PNG, MP4 or MOV</span>
          <input
            ref={inputRef}
            aria-label="Choose media file"
            type="file"
            accept=".jpg,.jpeg,.png,.mp4,.mov,image/jpeg,image/png,video/mp4,video/quicktime"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setError(null);
              setMessage(null);
            }}
          />
        </label>
        {file && (
          <div className="file-summary" aria-label="Selected file">
            <span className="file-type-icon" aria-hidden="true">{mediaTypeFor(file) === "video" ? "▶" : "◇"}</span>
            <span>
              <strong>{file.name}</strong>
              <small>{`${formatBytes(file.size)} · ${mediaTypeFor(file) === "video" ? "Video" : "Image"}`}</small>
            </span>
            <button type="button" className="button-link" onClick={clearSelection} disabled={uploading}>Remove</button>
          </div>
        )}
        <button type="submit" aria-label="Upload" disabled={uploading || !file}>{uploading ? "Preparing upload…" : "Upload to archive"}</button>
      </form>
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
