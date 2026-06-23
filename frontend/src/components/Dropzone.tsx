import { useRef, useState } from "react";

interface Props {
  busy: boolean;
  onFile: (f: File) => void;
}

export default function Dropzone({ busy, onFile }: Props) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  return (
    <div
      className={`drop ${over ? "over" : ""} ${busy ? "busy" : ""}`}
      onClick={() => !busy && ref.current?.click()}
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
        ref={ref}
        type="file"
        accept=".dxf,.dwg"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
        }}
      />
    </div>
  );
}
