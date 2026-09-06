export type ActivityStatus = "UNCHANGED" | "MODIFIED" | "ADDED" | "DELETED" | "POSSIBLE_RENAME" | "UNCERTAIN";
export type ProjectStatus = "MATCHED" | "ADDED" | "DELETED";

export interface EvidenceReference { evidence_id: string }
export interface EvidenceRecord {
  side: "before" | "after";
  table: string;
  line_number: number | null;
  fields: string[];
  values: string[];
  raw_line: string | null;
}
export interface ScheduleMetadata { source_id: string; source_name: string | null; encoding: string | null; project_count: number | null }
export interface ComparisonReport {
  schema_version: string;
  comparison: { before: ScheduleMetadata; after: ScheduleMetadata };
  projects: ProjectReport[];
  warnings: ReportWarning[];
  evidence: Record<string, EvidenceRecord>;
}
export interface ActivityMetadata {
  side: "before" | "after";
  activity_id: string;
  name: string | null;
  wbs_id: string | null;
  wbs_name: string | null;
  is_milestone: boolean;
  milestone_type: string | null;
  status: string | null;
  change_status: ActivityStatus | null;
  counterpart_activity_id: string | null;
  confidence: number | null;
  evidence_refs: EvidenceReference[];
}
export interface ActivityChangeReport {
  before_activity_id: string | null;
  after_activity_id: string | null;
  status: ActivityStatus;
  confidence: number;
  changes: Record<string, { before?: unknown; after?: unknown }>;
  evidence_refs: EvidenceReference[];
}
export interface RelationshipIdentity {
  predecessor_id: string | null;
  successor_id: string | null;
  relationship_type: string | null;
  lag_hours: string | null;
  occurrence: number;
}
export interface RelationshipChangeReport {
  status: string;
  identity_before: RelationshipIdentity | null;
  identity_after: RelationshipIdentity | null;
  ambiguous: boolean;
  evidence_refs: EvidenceReference[];
}
export interface MilestoneReport { activity_id: string; name: string | null; evidence_refs: EvidenceReference[] }
export interface PathReport {
  activity_ids: string[];
  node_metadata_refs: Record<string, string>;
  node_evidence_refs: Record<string, EvidenceReference>;
  edge_evidence_refs: EvidenceReference[];
}
export interface ImpactReport {
  source_activity: string;
  change_status: string;
  confidence: number;
  downstream_activity_count: number;
  changed_downstream_activities: string[];
  downstream_milestones: MilestoneReport[];
  relationship_changes: RelationshipChangeReport[];
  paths: PathReport[];
  evidence_refs: EvidenceReference[];
  uncertain: boolean;
}
export interface UncertainMatchReport { before_activity_id: string | null; after_activity_id: string | null; confidence: number; evidence_refs: EvidenceReference[] }
export interface UncertaintyReport { matches: UncertainMatchReport[]; excluded_from_impact: boolean }
export interface ReportWarning {
  code: string;
  severity: "INFO" | "WARNING" | "ERROR";
  message: string;
  project_id: string | null;
  activity_ids: string[];
  evidence_refs: EvidenceReference[];
}
export interface ProjectReport {
  project_id: string | null;
  status: ProjectStatus;
  activity_changes: ActivityChangeReport[];
  activity_metadata: Record<string, ActivityMetadata>;
  relationship_changes: RelationshipChangeReport[];
  impacts: ImpactReport[];
  uncertainty: UncertaintyReport | null;
  unresolved_relationships: Array<{ predecessor_id: string | null; successor_id: string | null; relationship_type: string | null; lag_hours: string | null; reason: string; evidence_refs: EvidenceReference[] }>;
  evidence_refs: EvidenceReference[];
  warnings: ReportWarning[];
}

export function isComparisonReport(value: unknown): value is ComparisonReport {
  if (!value || typeof value !== "object") return false;
  const report = value as Partial<ComparisonReport>;
  return (report.schema_version === "1.0" || report.schema_version === "1.1") && Array.isArray(report.projects) && typeof report.evidence === "object" && report.evidence !== null;
}

export function activityLabel(change: ActivityChangeReport): string {
  const nameEntry = Object.entries(change.changes).find(([field, values]) => /(^|_)(name|description|title)($|_)/i.test(field) && (typeof values.after === "string" || typeof values.before === "string"));
  if (nameEntry) return String(nameEntry[1].after ?? nameEntry[1].before ?? "Unknown activity");
  return String(change.after_activity_id ?? change.before_activity_id ?? "Unknown activity");
}
