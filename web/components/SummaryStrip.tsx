import { ComparisonReport } from "../lib/types";

export function SummaryStrip({ report }: { report: ComparisonReport }) {
  const activityChanges = report.projects.reduce((total, project) => total + project.activity_changes.length, 0);
  const relationshipChanges = report.projects.reduce((total, project) => total + project.relationship_changes.length, 0);
  return <div className="summary-strip">
    <div className="summary-item"><span className="summary-symbol">◈</span><span><small>Schema</small><strong>{report.schema_version}</strong></span></div>
    <div className="summary-item"><span className="summary-symbol">□</span><span><small>Projects</small><strong>{report.projects.length}</strong></span></div>
    <div className="summary-item summary-changed"><span className="summary-symbol">◌</span><span><small>Activity changes</small><strong>{activityChanges}</strong></span></div>
    <div className="summary-item summary-changed"><span className="summary-symbol">↗</span><span><small>Relationship changes</small><strong>{relationshipChanges}</strong></span></div>
    <div className="summary-item summary-warning"><span className="summary-symbol">△</span><span><small>Warnings</small><strong>{report.warnings.length + report.projects.reduce((n, project) => n + project.warnings.length, 0)}</strong></span></div>
    <div className="summary-item summary-evidence"><span className="summary-symbol">▤</span><span><small>Evidence</small><strong>{Object.keys(report.evidence).length}</strong></span></div>
  </div>;
}
