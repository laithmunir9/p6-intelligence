import { useState } from "react";
import { ActivityChangeReport, EvidenceReference, activityLabel } from "../lib/types";

function statusClass(status: string) { return `status status-${status.toLowerCase().replaceAll("_", "-")}`; }
function changeField(change: ActivityChangeReport) { return Object.keys(change.changes)[0]?.replaceAll("_", " ") ?? "—"; }
function changeValue(change: ActivityChangeReport) { const key = Object.keys(change.changes)[0]; return key ? `${change.changes[key]?.before ?? "—"} → ${change.changes[key]?.after ?? "—"}` : "—"; }

export function ActivityTable({ changes, selected, onSelect, onEvidence }: { changes: ActivityChangeReport[]; selected: ActivityChangeReport | null; onSelect: (change: ActivityChangeReport) => void; onEvidence: (reference: EvidenceReference) => void }) {
  const [query, setQuery] = useState("");
  const prioritized = [...changes].sort((a, b) => Number(a.status === "UNCHANGED") - Number(b.status === "UNCHANGED"));
  const visible = prioritized.filter((change) => `${activityLabel(change)} ${change.before_activity_id ?? ""} ${change.after_activity_id ?? ""}`.toLowerCase().includes(query.toLowerCase()));
  return <section className="table-section panel">
    <div className="section-tabs"><div className="tab active">Activity changes <span>{changes.length}</span></div><div className="tab">Relationships</div><div className="tab">Warnings</div></div>
    <div className="table-toolbar"><div className="search-box"><span aria-hidden="true">⌕</span><input aria-label="Search activities" placeholder="Search activities…" value={query} onChange={(event) => setQuery(event.target.value)} /></div><span className="result-count">{visible.length} of {changes.length} activities</span></div>
    <div className="activity-table" role="table" aria-label="Activity changes"><div className="activity-header" role="row"><span>Status</span><span>Activity ID</span><span>Activity name</span><span>Change</span><span>Primary field</span><span>Evidence</span><span /></div>
      {visible.length === 0 && <div className="table-empty">{changes.length === 0 ? "No activity changes were returned." : "No activities match this search."}</div>}
      {visible.map((change, index) => <button key={`${change.before_activity_id}-${change.after_activity_id}-${index}`} className={`activity-row ${selected === change ? "selected" : ""}`} onClick={() => onSelect(change)} aria-label={`Inspect ${activityLabel(change)}, ${change.status}`} role="row"><span><em className={statusClass(change.status)}>{change.status}</em></span><span className="mono">{change.after_activity_id ?? change.before_activity_id ?? "—"}</span><span className="activity-name">{activityLabel(change)}</span><span className="change-value" title={changeValue(change)}>{change.status === "UNCHANGED" ? "—" : change.status === "ADDED" || change.status === "DELETED" ? change.status : changeField(change)}</span><span className="change-field">{change.status === "UNCHANGED" ? "—" : changeField(change)}</span><span className="evidence-links">{change.evidence_refs.length > 0 ? change.evidence_refs.map((reference) => <span role="button" tabIndex={0} aria-label={`Open evidence ${reference.evidence_id}`} key={reference.evidence_id} onClick={(event) => { event.stopPropagation(); onEvidence(reference); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); onEvidence(reference); } }}>▧</span>) : "—"}</span><span className="row-arrow" aria-hidden="true">›</span></button>)}
    </div>
  </section>;
}
