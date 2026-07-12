// Shared UI primitives ตาม design spec studio (docs/reports/swarmsight-research-v2.md §5)
// กฎเหล็ก UI: metric ทุกตัวต้องมี InfoTip อธิบายสูตร inline (TRUST-09/NFR-08)
import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  desc,
  right,
}: {
  eyebrow: string;
  title: string;
  desc?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3 flex-wrap">
      <div>
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          <span className="text-primary">✦</span> {eyebrow}
        </div>
        <h1 className="mt-1 font-display text-4xl font-semibold leading-tight">{title}</h1>
        {desc && <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{desc}</p>}
      </div>
      {right}
    </div>
  );
}

// Tooltip อธิบายสูตร — ใช้ native title (เหมือน studio) เบาและ accessible พอสำหรับ desktop
export function InfoTip({ text }: { text: string }) {
  return (
    <span
      className="inline-block cursor-help select-none align-middle text-muted-foreground/70 hover:text-muted-foreground"
      title={text}
    >
      ⓘ
    </span>
  );
}

// Tab bar แบบ studio run detail: เส้นใต้ primary ที่ tab ที่เลือก
export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: T; label: string }[];
  active: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="flex gap-1 border-b border-border">
      {tabs.map((tb) => (
        <button
          key={tb.id}
          onClick={() => onChange(tb.id)}
          className={`-mb-px border-b-2 px-4 py-2 text-sm transition ${
            active === tb.id
              ? "border-primary font-medium text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          {tb.label}
        </button>
      ))}
    </div>
  );
}

// Selection card แบบ studio: เลือกแล้ว = border-primary bg-primary/5
export function SelectCard({
  active,
  onClick,
  children,
  className = "",
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-xl border p-3 text-left transition ${
        active ? "border-primary bg-primary/5" : "border-border bg-card hover:bg-muted"
      } ${className}`}
    >
      {children}
    </button>
  );
}

// Slider พร้อม label + ค่าปัจจุบัน — ใช้ใน persona pack editor (แก้ share/priors/media diet)
export function Slider({
  label,
  value,
  onChange,
  min = 0,
  max = 1,
  step = 0.05,
  display,
}: {
  label: ReactNode;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  display?: string;
}) {
  return (
    <label className="block text-xs">
      <span className="flex items-center justify-between text-muted-foreground">
        <span>{label}</span>
        <span className="tabular-nums font-medium text-foreground">{display ?? value.toFixed(2)}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="mt-1 w-full accent-primary"
      />
    </label>
  );
}
