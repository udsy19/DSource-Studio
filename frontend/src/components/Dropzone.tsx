import { useState } from "react";

interface Props {
  busy: boolean;
  onFile: (f: File) => void;
}

// A native <label> wraps the file input, so a click opens the OS file dialog with NO programmatic
// .click() — the bulletproof pattern that works across every browser. Drag-and-drop is also handled.
export default function Dropzone({ busy, onFile }: Props) {
  const [over, setOver] = useState(false);

  return (
    <label
      className={`drop ${over ? "over" : ""} ${busy ? "busy" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f && !busy) onFile(f);
      }}
    >
      <span className="lead">{busy ? "Reading the plate…" : "Drop a floor plate"}</span>
      <small>.dxf / .dwg · or click to browse</small>
      <input
        type="file"
        accept=".dxf,.dwg"
        className="sr-file"
        disabled={busy}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = ""; // allow re-selecting the same file
        }}
      />
    </label>
  );
}
