import { useState, type FormEvent } from "react";

import { useAuth } from "../auth/AuthContext";
import { MediaThumbnail } from "../library/MediaThumbnail";
import type { MediaResult } from "../library/MediaGallery";

export type QueryMode = "tags" | "species" | "thumbnail";

export interface QueryResult {
  media_id: string;
  file_name?: string | null;
  media_type: "image" | "video";
  status: MediaResult["status"];
  original_url: string | null;
  thumbnail_url: string | null;
  tag_counts: Record<string, number>;
  manual_tags?: string[];
  failure_code?: string | null;
  failure_message?: string | null;
}

export interface QueryResponse {
  results: QueryResult[];
}

export interface QueryClient {
  search(
    mode: QueryMode,
    payload: Record<string, unknown>,
    accessToken: string,
  ): Promise<QueryResponse>;
}

interface TagRow {
  species: string;
  count: string;
}

function displaySpecies(value: string): string {
  return value.replaceAll("_", " ");
}

function resultName(result: QueryResult): string {
  if (result.file_name) return result.file_name;
  if (result.original_url) {
    try {
      const path = new URL(result.original_url).pathname;
      const name = decodeURIComponent(path.split("/").at(-1) ?? "");
      if (name) return name;
    } catch {
      // Keep the query results usable if a malformed signed URL is returned.
    }
  }
  return `${result.media_type === "image" ? "Image" : "Video"} ${result.media_id.slice(0, 8)}`;
}

function statusLabel(status: QueryResult["status"]): string {
  if (status === "ready") return "Ready";
  if (status === "failed") return "Failed";
  if (status === "prepared") return "Detecting species";
  if (status === "deleting") return "Deleting";
  return "Processing";
}

function statusDescription(status: QueryResult["status"]): string {
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

export function QueryPanel({ client }: { client: QueryClient }) {
  const auth = useAuth();
  const [mode, setMode] = useState<QueryMode>("tags");
  const [rows, setRows] = useState<TagRow[]>([{ species: "", count: "1" }]);
  const [species, setSpecies] = useState("");
  const [thumbnailUrl, setThumbnailUrl] = useState("");
  const [results, setResults] = useState<QueryResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function updateRow(index: number, field: keyof TagRow, value: string) {
    setRows((current) =>
      current.map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row)),
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!auth.accessToken) {
      setError("Sign in before running a query.");
      return;
    }

    let payload: Record<string, unknown>;
    if (mode === "tags") {
      payload = Object.fromEntries(
        rows
          .map((row) => [row.species.trim().toLocaleLowerCase(), Number(row.count)] as const)
          .filter(([tag, count]) => tag.length > 0 && Number.isInteger(count) && count > 0),
      );
      if (Object.keys(payload).length !== rows.length) {
        setError("Every tag needs a species and a positive whole-number count.");
        return;
      }
    } else if (mode === "species") {
      if (!species.trim()) {
        setError("Enter a species name.");
        return;
      }
      payload = { species: species.trim() };
    } else {
      if (!thumbnailUrl.trim()) {
        setError("Enter a thumbnail URL.");
        return;
      }
      payload = { thumbnail_url: thumbnailUrl.trim() };
    }

    setLoading(true);
    setError(null);
    try {
      const response = await client.search(mode, payload, auth.accessToken);
      setResults(response.results);
    } catch (caught) {
      setResults(null);
      setError(caught instanceof Error ? caught.message : "Query failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby="query-heading">
      <div className="panel-heading">
        <div>
          <p className="panel-kicker">Explore the archive</p>
          <h2 id="query-heading">Search wildlife media</h2>
        </div>
        <span className="panel-number" aria-hidden="true">03</span>
      </div>
      <p className="panel-description">Combine detected species counts, browse one species, or use an existing thumbnail to find related observations.</p>
      <form className="query-form" onSubmit={submit}>
        <fieldset className="mode-switcher">
          <legend>Query type</legend>
          <label className={mode === "tags" ? "active" : ""}>
            <input aria-label="Tag counts" name="query-mode" type="radio" checked={mode === "tags"} onChange={() => setMode("tags")} />
            <span><strong>Tag counts</strong><small>Match a combination</small></span>
          </label>
          <label className={mode === "species" ? "active" : ""}>
            <input aria-label="Species" name="query-mode" type="radio" checked={mode === "species"} onChange={() => setMode("species")} />
            <span><strong>Species</strong><small>Browse one label</small></span>
          </label>
          <label className={mode === "thumbnail" ? "active" : ""}>
            <input
              name="query-mode"
              aria-label="Thumbnail URL"
              type="radio"
              checked={mode === "thumbnail"}
              onChange={() => setMode("thumbnail")}
            />
            <span><strong>Thumbnail URL</strong><small>Find related media</small></span>
          </label>
        </fieldset>

        {mode === "tags" && (
          <div className="tag-query-builder">
            {rows.map((row, index) => (
              <div className="tag-query-row" key={index}>
                <label>
                  Species {index + 1}
                  <input
                    aria-label={`Species ${index + 1}`}
                    value={row.species}
                    onChange={(event) => updateRow(index, "species", event.target.value)}
                  />
                </label>
                <label>
                  Minimum count {index + 1}
                  <input
                    aria-label={`Minimum count ${index + 1}`}
                    type="number"
                    min="1"
                    step="1"
                    value={row.count}
                    onChange={(event) => updateRow(index, "count", event.target.value)}
                  />
                </label>
                {rows.length > 1 && (
                  <button className="secondary" type="button" onClick={() => setRows((current) => current.filter((_, i) => i !== index))}>
                    Remove tag {index + 1}
                  </button>
                )}
              </div>
            ))}
            <button className="secondary add-row-button" type="button" onClick={() => setRows((current) => [...current, { species: "", count: "1" }])}>
              Add tag
            </button>
          </div>
        )}

        {mode === "species" && (
          <label>
            Species name
            <input aria-label="Species name" value={species} onChange={(event) => setSpecies(event.target.value)} />
          </label>
        )}

        {mode === "thumbnail" && (
          <label>
            Thumbnail URL
            <input
              aria-label="Thumbnail URL"
              type="url"
              value={thumbnailUrl}
              onChange={(event) => setThumbnailUrl(event.target.value)}
            />
          </label>
        )}

        <button className="query-submit" type="submit" disabled={loading}>{loading ? "Searching…" : "Search"}</button>
      </form>

      {error && <p role="alert">{error}</p>}
      {results?.length === 0 && <p className="empty-state">No matching media found.</p>}
      {results && results.length > 0 && (
        <div className="query-results">
          <p className="result-summary" role="status">{`${results.length} ${results.length === 1 ? "match" : "matches"} found`}</p>
          <ul className="media-grid" aria-label="Query results">
            {results.map((result) => {
              const name = resultName(result);
              return (
                <li className={`media-card media-card-${result.status}`} key={result.media_id}>
                  <div className="media-preview">
                    <MediaThumbnail media={result} name={name} />
                    <span className={`status-chip status-${result.status}`}>{statusLabel(result.status)}</span>
                  </div>
                  <div className="media-card-body">
                    <div className="media-card-title"><strong title={name}>{name}</strong><span>{`ID: ${result.media_id.slice(0, 8)}`}</span></div>
                    <p className={`media-status-copy media-status-${result.status}`}>{statusDescription(result.status)}</p>
                    <div className="media-tags">
                      <div>
                        <span className="tag-group-label">Detected species</span>
                        {Object.keys(result.tag_counts).length > 0 ? <div className="tag-list">{Object.entries(result.tag_counts).map(([tag, count]) => <span className="tag-chip" key={`detected-${tag}`}>{`${displaySpecies(tag)} × ${count}`}</span>)}</div> : <span className="tag-empty">None detected yet</span>}
                      </div>
                      {(result.manual_tags ?? []).length > 0 && <div><span className="tag-group-label">Manual tags</span><div className="tag-list">{(result.manual_tags ?? []).map((tag) => <span className="tag-chip tag-chip-manual" key={`manual-${tag}`}>{displaySpecies(tag)}</span>)}</div></div>}
                    </div>
                    {result.status === "failed" && (
                      <div className="media-failure-summary">
                        <strong>{failureSummary(result.failure_code)}</strong>
                        {result.failure_code && <code>{result.failure_code}</code>}
                        {result.failure_message && <details><summary>View technical details</summary><p>{result.failure_message}</p></details>}
                      </div>
                    )}
                    <div className="media-card-actions">
                      {result.original_url && <a className="button button-secondary" href={result.original_url} target="_blank" rel="noreferrer">View original</a>}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}
