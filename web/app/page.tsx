"use client";

import { ChangeEvent, DragEvent, useMemo, useRef, useState } from "react";
import { ActivityTable } from "../components/ActivityTable";
import { EvidencePanel } from "../components/EvidencePanel";
import { ImpactInspector } from "../components/ImpactInspector";
import { RelationshipSection } from "../components/RelationshipSection";
import { SummaryStrip } from "../components/SummaryStrip";
import { UploadRail } from "../components/UploadRail";
import { WarningSection } from "../components/WarningSection";
import { ApiError, compareSchedules } from "../lib/api";
import { DEMO_LABEL, loadDemoFiles } from "../lib/demo";
import { ActivityChangeReport, ComparisonReport, EvidenceReference } from "../lib/types";

const MAX_FILE_BYTES = 25 * 1024 * 1024;

export default function Home() {
  const [before, setBefore] = useState<File | null>(null);
  const [after, setAfter] = useState<File | null>(null);
  const [report, setReport] = useState<ComparisonReport | null>(null);
  const [selected, setSelected] = useState<ActivityChangeReport | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceReference | null>(null);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const allActivityChanges = useMemo(() => report?.projects.flatMap((project) => project.activity_changes) ?? [], [report]);
  const selectedProject = useMemo(() => report?.projects.find((project) => project.activity_changes.includes(selected as ActivityChangeReport)) ?? report?.projects[0] ?? null, [report, selected]);
  const selectedImpact = useMemo(() => selectedProject?.impacts.find((impact) => impact.source_activity === selected?.before_activity_id || impact.source_activity === selected?.after_activity_id) ?? null, [selectedProject, selected]);

  function validateFile(file: File | null): string | null {
    if (!file) return null;
    if (!file.name.toLowerCase().endsWith(".xer")) return "Choose an XER export file.";
    if (file.size > MAX_FILE_BYTES) return "Each XER file must be 25 MiB or smaller.";
    return null;
  }

  function assignFile(side: "before" | "after", file: File | null) {
    const validationError = validateFile(file);
    if (validationError) { setError({ code: "INVALID_FILE", message: validationError }); return; }
    setError(null);
    if (side === "before") setBefore(file); else setAfter(file);
    setReport(null);
    setSelected(null);
  }

  function onFileChange(side: "before" | "after", event: ChangeEvent<HTMLInputElement>) { assignFile(side, event.target.files?.[0] ?? null); }
  function onDrop(side: "before" | "after", event: DragEvent<HTMLDivElement>) { event.preventDefault(); assignFile(side, event.dataTransfer.files?.[0] ?? null); }

  async function compareFiles(beforeFile: File, afterFile: File) {
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setLoading(true); setError(null); setSelectedEvidence(null);
    try {
      const nextReport = await compareSchedules(beforeFile, afterFile, abortRef.current.signal);
      setReport(nextReport);
      const firstMeaningfulChange = nextReport.projects.flatMap((project) => project.activity_changes).find((activity) => activity.status !== "UNCHANGED");
      setSelected(firstMeaningfulChange ?? nextReport.projects[0]?.activity_changes[0] ?? null);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      const apiError = caught as ApiError;
      setError({ code: apiError.code ?? "INTERNAL_ERROR", message: apiError.message ?? "The comparison could not be completed." });
    } finally { setLoading(false); }
  }

  async function compare() {
    if (!before || !after) { setError({ code: "MISSING_UPLOAD", message: "Select both a before and after XER file to compare." }); return; }
    await compareFiles(before, after);
  }

  async function tryDemo() {
    setDemoLoading(true); setError(null);
    try {
      const demo = await loadDemoFiles();
      setBefore(demo.before); setAfter(demo.after);
      await compareFiles(demo.before, demo.after);
    } catch (caught) {
      setError({ code: "DEMO_LOAD_FAILED", message: caught instanceof Error ? caught.message : "The synthetic demo could not be loaded." });
    } finally { setDemoLoading(false); }
  }

  function clear() { abortRef.current?.abort(); setBefore(null); setAfter(null); setReport(null); setSelected(null); setSelectedEvidence(null); setError(null); }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark" aria-hidden="true">⌬</span><span>P6 Intelligence</span></div>
        <div className="topbar-status"><span className="status-dot" /> Read-only analysis <span className="topbar-divider" /> Schema {report?.schema_version ?? "1.1"}</div>
      </header>
      <div className="app-content">
        <section className="intro-row">
          <div><div className="eyebrow">Read-only schedule analysis</div><h1>Compare schedule updates</h1><p>Trace activity and relationship changes through downstream dependencies, with source-level evidence.</p></div>
          <div className="intro-actions">{!report && <button className="button button-demo" onClick={tryDemo} disabled={loading || demoLoading}><span aria-hidden="true">▷</span>{demoLoading ? "Loading demo…" : "Try synthetic demo"}</button>}{report && <button className="button button-quiet" onClick={clear}>Clear and start over</button>}</div>
        </section>
        <UploadRail before={before} after={after} loading={loading} onChange={onFileChange} onDrop={onDrop} onCompare={compare} />
        {!report && !loading && <p className="demo-note"><span className="demo-badge">{DEMO_LABEL}</span> A small substation expansion scenario with transformer delivery, commissioning, and energization changes.</p>}
        {error && <div className="error-banner" role="alert"><strong>{error.code}</strong><span>{error.message}</span></div>}
        {loading && <div className="loading-bar" role="status"><span className="loading-pulse" /> Comparing schedules… Free Render may take a moment to wake up.</div>}
        {report && <>
          <SummaryStrip report={report} />
          <section className="analysis-grid">
            <div className="analysis-main">
              <ActivityTable changes={allActivityChanges} evidence={report.evidence} selected={selected} onSelect={setSelected} onEvidence={setSelectedEvidence} />
              <RelationshipSection projects={report.projects} onEvidence={setSelectedEvidence} />
              <WarningSection warnings={report.warnings} projects={report.projects} onEvidence={setSelectedEvidence} />
            </div>
            <aside className="inspector-column">
              <ImpactInspector change={selected} project={selectedProject} impact={selectedImpact} onEvidence={setSelectedEvidence} />
              <EvidencePanel reference={selectedEvidence} evidence={report.evidence} onClose={() => setSelectedEvidence(null)} />
            </aside>
          </section>
        </>}
        {!report && !loading && <section className="empty-note"><span className="empty-line" /><p>Upload two XER exports to inspect deterministic activity and dependency changes.</p><span className="empty-line" /></section>}
      </div>
    </main>
  );
}
