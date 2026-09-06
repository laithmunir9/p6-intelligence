import { ActivityChangeReport, EvidenceReference, ImpactReport, ProjectReport, RelationshipChangeReport } from "../lib/types";

function relationshipLabel(relationship: RelationshipChangeReport | undefined) {
  const identity = relationship?.identity_after ?? relationship?.identity_before;
  if (!identity) return "—";
  return `${identity.relationship_type?.replace("PR_", "") ?? "Dependency"} · ${identity.lag_hours ?? "0"}h`;
}

export function ImpactInspector({ change, project, impact, onEvidence }: { change: ActivityChangeReport | null; project: ProjectReport | null; impact: ImpactReport | null; onEvidence: (reference: EvidenceReference) => void }) {
  if (!change) return <section className="inspector panel empty-inspector"><div className="empty-inspector-mark">⌁</div><h2>Select an activity</h2><p>Choose a change to inspect downstream context and source evidence.</p></section>;
  const paths = impact?.paths ?? [];
  const nodes = Array.from(new Set(paths.flatMap((path) => path.activity_ids))).slice(0, 8);
  const source = change.after_activity_id ?? change.before_activity_id ?? "Unknown";
  const edgeByPair = new Map<string, RelationshipChangeReport>();
  for (const relationship of project?.relationship_changes ?? []) {
    const identity = relationship.identity_after ?? relationship.identity_before;
    if (identity?.predecessor_id && identity.successor_id) edgeByPair.set(`${identity.predecessor_id}->${identity.successor_id}`, relationship);
  }
  return <section className="inspector panel"><div className="inspector-heading"><div><span className="inspector-kicker">Selected activity</span><h2>{source}</h2><p>{change.status} · confidence {(change.confidence * 100).toFixed(0)}%</p></div><em className={"status " + `status-${change.status.toLowerCase().replaceAll("_", "-")}`}>{change.status}</em></div>
    <div className="inspector-change">{Object.entries(change.changes).slice(0, 2).map(([field, values]) => <div key={field}><span>Changed field</span><strong>{field.replaceAll("_", " ")}</strong><small>{String(values.before ?? "—")} → {String(values.after ?? "—")}</small></div>)}</div>
    <div className="inspector-title">Downstream of this activity</div>
    {impact ? <><div className="impact-explainer">{impact.paths.length > 0 ? <>This activity sits upstream of <strong>{impact.downstream_milestones[0]?.name ?? "a downstream milestone"}</strong> through the path shown below.</> : "No dependency path to a milestone was returned for this activity."} <span>Impact describes dependency context; it does not claim schedule causality.</span></div><div className="impact-stats"><div><strong>{impact.downstream_activity_count}</strong><span>downstream activities</span></div><div><strong>{impact.changed_downstream_activities.length}</strong><span>changed downstream</span></div><div><strong>{impact.downstream_milestones.length}</strong><span>milestones</span></div></div><div className="graph" aria-label="Dependency path from selected activity"><div className="graph-caption">Dependency path · source → downstream milestone</div><div className="graph-line" />{nodes.length ? nodes.map((node, index) => { const previous = nodes[index - 1]; const relationship = previous ? edgeByPair.get(`${previous}->${node}`) : undefined; const milestone = impact.downstream_milestones.some((item) => item.activity_id === node); const changed = node === source || impact.changed_downstream_activities.includes(node); return <div key={`${node}-${index}`} className="graph-step"><div className={`graph-node ${milestone ? "node-milestone" : changed ? "node-changed" : "node-context"}`}><b>{node}</b><small>{milestone ? (changed ? "Changed milestone" : "Milestone") : changed ? (node === source ? "Changed source" : "Changed downstream") : "Downstream"}</small></div>{index < nodes.length - 1 && <span className="graph-arrow" aria-hidden="true">→</span>}{index < nodes.length - 1 && <span className="graph-edge">{relationshipLabel(relationship)}</span>}</div> }) : <p className="graph-empty">No dependency paths were returned for this activity.</p>}</div><div className="inspector-list"><div><span>Available paths</span><strong>{impact.paths.length}</strong></div><div><span>Uncertainty</span><strong>{impact.uncertain ? "Present" : "None reported"}</strong></div></div></> : <div className="no-impact">No impact context was returned for this activity.</div>}
    <div className="inspector-evidence-title">Evidence references <span>{change.evidence_refs.length}</span></div><div className="evidence-ref-list">{change.evidence_refs.map((reference) => <button key={reference.evidence_id} onClick={() => onEvidence(reference)}>{reference.evidence_id} <span>Open source record →</span></button>)}</div>
  </section>;
}
