import { ChangeEvent, DragEvent, useRef } from "react";

interface Props {
  before: File | null;
  after: File | null;
  loading: boolean;
  onChange: (side: "before" | "after", event: ChangeEvent<HTMLInputElement>) => void;
  onDrop: (side: "before" | "after", event: DragEvent<HTMLDivElement>) => void;
  onCompare: () => void;
}

function UploadBox({ side, file, onChange, onDrop }: { side: "before" | "after"; file: File | null; onChange: Props["onChange"]; onDrop: Props["onDrop"] }) {
  const inputRef = useRef<HTMLInputElement>(null);
  return <div className="upload-group">
    <label htmlFor={`${side}-file`}>{side === "before" ? "Before schedule" : "After schedule"}</label>
    <div className={`upload-box ${file ? "has-file" : ""}`} onDragOver={(event) => event.preventDefault()} onDrop={(event) => onDrop(side, event)} onClick={() => inputRef.current?.click()} role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") inputRef.current?.click(); }}>
      <input ref={inputRef} id={`${side}-file`} type="file" accept=".xer,application/octet-stream" onChange={(event) => onChange(side, event)} />
      <span className="upload-icon" aria-hidden="true">↑</span>
      <span className="upload-prompt">{file ? "Replace XER file" : "Drop XER file here"}</span>
      <span className="upload-or">or</span>
      <span className="button button-small">Browse files</span>
    </div>
    <div className="file-row" aria-live="polite"><span className="file-icon" aria-hidden="true">▧</span><span className="file-name">{file?.name ?? "No file selected"}</span>{file && <><span className="file-size">{(file.size / 1024 / 1024).toFixed(1)} MiB</span><span className="file-ok">✓</span></>}</div>
  </div>;
}

export function UploadRail(props: Props) {
  return <section className="upload-rail">
    <UploadBox side="before" file={props.before} onChange={props.onChange} onDrop={props.onDrop} />
    <UploadBox side="after" file={props.after} onChange={props.onChange} onDrop={props.onDrop} />
    <div className="compare-action"><button className="button button-primary" disabled={props.loading} onClick={props.onCompare}><span aria-hidden="true">⇄</span>{props.loading ? "Comparing…" : "Compare schedules"}</button></div>
  </section>;
}
