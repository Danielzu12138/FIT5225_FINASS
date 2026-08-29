import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { BulkDeleteResponse, SingleDeleteResponse, TagUpdateResponse } from "../api/mediaTypes";
import { useAuth } from "../auth/AuthContext";
import { MediaThumbnail } from "./MediaThumbnail";

export interface MediaResult {
  media_id: string;
  media_type: "image" | "video";
  status: "reserved" | "uploaded" | "processing" | "prepared" | "ready" | "deleting" | "failed";
  original_url: string | null;
  thumbnail_url: string | null;
  tag_counts: Record<string, number>;
  manual_tags?: string[];
  failure_code?: string | null;
  failure_message?: string | null;
}

export interface LocalMediaPreview {
  file_name: string;
  url: string;
}

export interface MediaLibraryClient {
  list(accessToken: string): Promise<{ results: MediaResult[] }>;
  updateTags(urls: string[], tags: string[], operation: 0 | 1, accessToken: string): Promise<TagUpdateResponse>;
  deleteMedia(urls: string[], accessToken: string): Promise<BulkDeleteResponse>;
  deleteMediaById(mediaId: string, accessToken: string): Promise<SingleDeleteResponse>;
}

type MediaFilter = "all" | "image" | "video";
type StatusFilter = "all" | "ready" | "processing" | "failed";

const PROCESSING_STATUSES = new Set<MediaResult["status"]>([
  "reserved", "uploaded", "processing", "prepared", "deleting",
]);

function displaySpecies(value: string): string {
  return value.replaceAll("_", " ");
}

function fileName(media: MediaResult, localPreview?: LocalMediaPreview): string {
  if (localPreview?.file_name) return localPreview.file_name;
  if (media.original_url) {
    try {
      const path = new URL(media.original_url).pathname;
      const name = decodeURIComponent(path.split("/").at(-1) ?? "");
      if (name) return name;
    } catch {
      // A malformed signed URL should not prevent the rest of the card rendering.
    }
  }
  return `${media.media_type === "image" ? "Image" : "Video"} ${media.media_id.slice(0, 8)}`;
}

function statusLabel(status: MediaResult["status"]): string {
  if (status === "ready") return "Ready";
  if (status === "failed") return "Failed";
  if (status === "prepared") return "Detecting species";
  if (status === "deleting") return "Deleting";
  return "Processing";
}

function statusDescription(status: MediaResult["status"]): string {
  if (status === "ready") return "Analysis complete";
  if (status === "prepared") return "Detecting species";
  if (status === "failed") return "Processing failed";
  if (status === "deleting") return "Deletion in progress";
  return "Preparing preview";
}

function failureSummary(code?: string | null): string {
  if (code?.startsWith("TAGGING_")) return "Species detection failed.";
  if (code?.startsWith("IMAGE_")) return "Image processing failed.";
  if (code?.startsWith("VIDEO_")) return "Video processing failed.";
  return "Media processing failed.";
}

function matchesStatus(media: MediaResult, filter: StatusFilter): boolean {
  if (filter === "all") return true;
  if (filter === "processing") return PROCESSING_STATUSES.has(media.status);
  return media.status === filter;
}

export function MediaGallery({
  client,
  refreshVersion = 0,
  localPreviews = {},
  onResultsChange,
}: {
  client: MediaLibraryClient;
  refreshVersion?: number;
  localPreviews?: Record<string, LocalMediaPreview>;
  onResultsChange?(results: MediaResult[]): void;
}) {
  const auth = useAuth();
  const [results, setResults] = useState<MediaResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [filter, setFilter] = useState<MediaFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [tags, setTags] = useState("");
  const [deleting, setDeleting] = useState<MediaResult | null>(null);
  const [confirmingBulkDelete, setConfirmingBulkDelete] = useState(false);
  const pollTimer = useRef<number | undefined>(undefined);

  const loadMedia = useCallback(async () => {
    if (!auth.accessToken) {
      setResults(null);
      setLoading(false);
      setError(null);
      setMessage(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await client.list(auth.accessToken);
      setResults(response.results);
      onResultsChange?.(response.results);
      setSelected((current) => new Set([...current].filter((id) => response.results.some((item) => item.media_id === id))));
      const pending = response.results.some((item) => PROCESSING_STATUSES.has(item.status));
      if (pending && pollTimer.current === undefined) {
        pollTimer.current = window.setInterval(() => void loadMedia(), 5000);
      } else if (!pending && pollTimer.current !== undefined) {
        window.clearInterval(pollTimer.current);
        pollTimer.current = undefined;
      }
    } catch (caught) {
      setResults(null);
      setError(caught instanceof Error ? caught.message : "Media library is unavailable.");
    } finally {
      setLoading(false);
    }
  }, [auth.accessToken, client, onResultsChange]);

  useEffect(() => {
    void loadMedia();
    return () => {
      if (pollTimer.current !== undefined) window.clearInterval(pollTimer.current);
      pollTimer.current = undefined;
    };
  }, [loadMedia, refreshVersion]);

  const counts = useMemo(() => ({
    all: results?.length ?? 0,
    image: results?.filter((item) => item.media_type === "image").length ?? 0,
    video: results?.filter((item) => item.media_type === "video").length ?? 0,
    ready: results?.filter((item) => item.status === "ready").length ?? 0,
    processing: results?.filter((item) => PROCESSING_STATUSES.has(item.status)).length ?? 0,
    failed: results?.filter((item) => item.status === "failed").length ?? 0,
  }), [results]);
  const filtered = results?.filter((item) =>
    (filter === "all" || item.media_type === filter) && matchesStatus(item, statusFilter),
  ) ?? [];
  const selectedResults = results?.filter((item) => selected.has(item.media_id)) ?? [];
  const selectedUrls = selectedResults.flatMap((item) => item.original_url ? [item.original_url] : []);

  function replaceResults(next: MediaResult[]) {
    setResults(next);
    onResultsChange?.(next);
  }

  function toggle(mediaId: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(mediaId)) next.delete(mediaId);
      else next.add(mediaId);
      return next;
    });
  }

  function normalizedTags(): string[] {
    return [...new Set(tags.split(",").map((tag) => tag.trim().toLowerCase()).filter(Boolean))];
  }

  async function updateSelectedTags(operation: 0 | 1) {
    if (!auth.accessToken || selectedUrls.length === 0) return;
    const nextTags = normalizedTags();
    setMessage(null);
    if (nextTags.length === 0) {
      setError("Enter at least one tag.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await client.updateTags(selectedUrls, nextTags, operation, auth.accessToken);
      const updatedIds = new Set(response.results.filter((outcome) => outcome.status === "updated").map((outcome) => outcome.media_id));
      const next = (results ?? []).map((media) => {
        if (!updatedIds.has(media.media_id)) return media;
        const manual = new Set(media.manual_tags ?? []);
        nextTags.forEach((tag) => operation === 1 ? manual.add(tag) : manual.delete(tag));
        return { ...media, manual_tags: [...manual].sort() };
      });
      replaceResults(next);
      const failures = response.results.filter((outcome) => !["updated", "unchanged"].includes(outcome.status));
      if (failures.length > 0) setError(`Tags were not updated for ${failures.length} item(s).`);
      if (response.results.length > failures.length) setMessage("Selected media tags updated.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The tag update failed.");
    } finally {
      setLoading(false);
    }
  }

  async function deleteSelected() {
    if (!auth.accessToken || selectedResults.length === 0) return;
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const deletedIds = new Set<string>();
      const failures: string[] = [];
      if (selectedUrls.length > 0) {
        const response = await client.deleteMedia(selectedUrls, auth.accessToken);
        response.results.forEach((outcome) => {
          if (outcome.status === "deleted" && outcome.media_id) deletedIds.add(outcome.media_id);
          else failures.push(outcome.error || outcome.status);
        });
      }
      const withoutUrls = selectedResults.filter((item) => !item.original_url);
      const responses = await Promise.all(withoutUrls.map((item) => client.deleteMediaById(item.media_id, auth.accessToken!)));
      responses.forEach((response) => {
        if (response.result.status === "deleted" && response.result.media_id) deletedIds.add(response.result.media_id);
        else failures.push(response.result.error || response.result.status);
      });
      const next = (results ?? []).filter((item) => !deletedIds.has(item.media_id));
      replaceResults(next);
      setSelected((current) => new Set([...current].filter((id) => !deletedIds.has(id))));
      setConfirmingBulkDelete(false);
      if (deletedIds.size > 0) setMessage(`${deletedIds.size} selected item(s) deleted.`);
      if (failures.length > 0) setError(`Could not delete ${failures.length} item(s): ${failures.join("; ")}`);
    } catch (caught) {
      setConfirmingBulkDelete(false);
      setError(caught instanceof Error ? caught.message : "The selected media could not be deleted.");
    } finally {
      setLoading(false);
    }
  }

  async function confirmDelete() {
    if (!deleting || !auth.accessToken) return;
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const response = await client.deleteMediaById(deleting.media_id, auth.accessToken);
      if (response.result.status !== "deleted") {
        setError(response.result.error || `Media could not be deleted (${response.result.status}).`);
        setDeleting(null);
        return;
      }
      const next = (results ?? []).filter((item) => item.media_id !== deleting.media_id);
      replaceResults(next);
      setSelected((current) => {
        const updated = new Set(current);
        updated.delete(deleting.media_id);
        return updated;
      });
      setMessage("Media deleted.");
      setDeleting(null);
    } catch (caught) {
      setDeleting(null);
      setError(caught instanceof Error ? caught.message : "The media could not be deleted.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby="media-gallery-heading">
      <div className="panel-heading panel-heading-row">
        <div><p className="panel-kicker">Observation collection</p><h2 id="media-gallery-heading">Your media library</h2></div>
        <button type="button" className="button-link refresh-library" onClick={() => void loadMedia()} disabled={loading}>↻ Refresh</button>
      </div>
      <p className="panel-description">Review processing progress, open originals and organise the species evidence found in each file.</p>
      {loading && <p className="inline-loading" role="status">Updating library…</p>}
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {!loading && results?.length === 0 && <p className="empty-state">Your media library is empty. Upload a field observation to begin.</p>}
      {results && results.length > 0 && (
        <>
          <div className="library-filters">
            <div className="filter-bar" role="group" aria-label="Filter by media type">
              {(["all", "image", "video"] as const).map((value) => (
                <button key={value} type="button" className={filter === value ? "active" : "secondary"} aria-pressed={filter === value} onClick={() => setFilter(value)}>
                  {value === "all" ? `All ${counts.all}` : value === "image" ? `Images ${counts.image}` : `Videos ${counts.video}`}
                </button>
              ))}
            </div>
            <div className="filter-bar filter-bar-status" role="group" aria-label="Filter by processing status">
              {(["all", "ready", "processing", "failed"] as const).map((value) => (
                <button key={value} type="button" className={statusFilter === value ? "active" : "secondary"} aria-pressed={statusFilter === value} onClick={() => setStatusFilter(value)}>
                  {value === "all" ? "Any status" : `${value.charAt(0).toUpperCase()}${value.slice(1)} ${counts[value]}`}
                </button>
              ))}
            </div>
          </div>
          <div className="library-selection-toolbar" aria-label="Library selection actions">
            <div>
              <strong>{selected.size === 0 ? "Select media to manage" : `${selected.size} selected`}</strong>
              <button type="button" className="button-link" onClick={() => setSelected(new Set(filtered.map((item) => item.media_id)))}>Select visible</button>
              {selected.size > 0 && <button type="button" className="button-link" onClick={() => setSelected(new Set())}>Clear</button>}
            </div>
            {selected.size > 0 && (
              <div className="library-bulk-actions">
                <label htmlFor="library-tags">Tags</label>
                <input id="library-tags" value={tags} onChange={(event) => setTags(event.target.value)} placeholder="night, field-note" />
                <button type="button" disabled={loading || selectedUrls.length === 0} onClick={() => void updateSelectedTags(1)}>Add tags</button>
                <button type="button" className="secondary" disabled={loading || selectedUrls.length === 0} onClick={() => void updateSelectedTags(0)}>Remove tags</button>
                <button type="button" className="button-danger-subtle" disabled={loading} onClick={() => setConfirmingBulkDelete(true)}>Delete selected</button>
              </div>
            )}
          </div>
          {filtered.length === 0 ? <p className="empty-state">No media matches these filters.</p> : (
            <ul className="media-grid" aria-label="Media library">
              {filtered.map((media) => {
                const local = localPreviews[media.media_id];
                const name = fileName(media, local);
                return (
                  <li className={`media-card media-card-${media.status} ${selected.has(media.media_id) ? "selected" : ""}`} key={media.media_id}>
                    <div className="media-preview">
                      <MediaThumbnail media={media} name={name} localUrl={local?.url} />
                      <label className="media-select"><input type="checkbox" checked={selected.has(media.media_id)} onChange={() => toggle(media.media_id)} /><span>Select</span></label>
                      <span className={`status-chip status-${media.status}`}>{statusLabel(media.status)}</span>
                    </div>
                    <div className="media-card-body">
                      <div className="media-card-title"><strong title={name}>{name}</strong><span>{`ID: ${media.media_id.slice(0, 8)}`}</span></div>
                      <p className={`media-status-copy media-status-${media.status}`}>{statusDescription(media.status)}</p>
                      <div className="media-tags">
                        <div><span className="tag-group-label">Detected species</span>{Object.keys(media.tag_counts).length > 0 ? <div className="tag-list">{Object.entries(media.tag_counts).map(([tag, count]) => <span className="tag-chip" key={`detected-${tag}`}>{`${displaySpecies(tag)} × ${count}`}</span>)}</div> : <span className="tag-empty">None detected yet</span>}</div>
                        {(media.manual_tags ?? []).length > 0 && <div><span className="tag-group-label">Manual tags</span><div className="tag-list">{(media.manual_tags ?? []).map((tag) => <span className="tag-chip tag-chip-manual" key={`manual-${tag}`}>{displaySpecies(tag)}</span>)}</div></div>}
                      </div>
                      {media.status === "failed" && (
                        <div className="media-failure-summary">
                          <strong>{failureSummary(media.failure_code)}</strong>
                          {media.failure_code && <code>{media.failure_code}</code>}
                          {media.failure_message && <details><summary>View technical details</summary><p>{media.failure_message}</p></details>}
                        </div>
                      )}
                      <div className="media-card-actions">
                        {media.original_url && <a className="button button-secondary" href={media.original_url} target="_blank" rel="noreferrer">View original</a>}
                        <button type="button" className="button-danger-subtle" disabled={loading} onClick={() => setDeleting(media)}>Delete</button>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
      {(deleting || confirmingBulkDelete) && (
        <div className="modal-backdrop">
          <div className="dialog" role="dialog" aria-label="Confirm deletion" aria-modal="true">
            <p>{deleting ? `Delete ${fileName(deleting, localPreviews[deleting.media_id])} from your library?` : `Delete ${selectedResults.length} selected item(s)?`} This cannot be undone.</p>
            <div className="dialog-actions">
              <button className="secondary" type="button" disabled={loading} onClick={() => { setDeleting(null); setConfirmingBulkDelete(false); }}>Cancel</button>
              <button className="button-danger" type="button" disabled={loading} onClick={() => void (deleting ? confirmDelete() : deleteSelected())}>Confirm delete</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
