import { EvidenceRecord, EvidenceReference } from "../lib/types";

export function EvidencePanel({ reference, evidence, onClose }: { reference: EvidenceReference | null; evidence: Record<string, EvidenceRecord>; onClose: () => void }) {
  const record = reference ? evidence[reference.evidence_id] : null;
  if (!record) return null;
  return <section className="evidence-panel panel" aria-label="Source evidence"><div className="evidence-panel-heading"><div><span className="inspector-kicker">Source evidence</span><h2>{record.side === "before" ? "Before source" : "After source"}</h2><p className="evidence-proof">This conclusion is traceable to this exact XER record.</p></div><button className="icon-button" aria-label="Close evidence" onClick={onClose}>×</button></div><div className="evidence-meta"><span><small>Side</small><strong>{record.side === "before" ? "Previous" : "Current"}</strong></span><span><small>Table</small><strong>{record.table}</strong></span><span><small>Line</small><strong>{record.line_number ?? "—"}</strong></span></div><div className="evidence-fields">{record.fields.map((field, index) => <div key={`${field}-${index}`}><span>{field}</span><strong>{record.values[index] ?? ""}</strong></div>)}</div><div className="raw-record"><div>Original raw record</div><pre>{record.raw_line ?? "No raw line available"}</pre></div></section>;
}
