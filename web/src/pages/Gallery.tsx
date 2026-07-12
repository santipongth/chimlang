import { useEffect, useState } from "react";
import { GalleryDetail, GalleryListItem, fetchGallery, fetchGalleryDetail, pct, voteGallery } from "../api";
import { useLang } from "../i18n";
import { InfoTip, PageHeader } from "../ui";

// Public Gallery (P5-M8, ADR-0004) — ผลรันที่เผยแพร่ + โหวต agree/disagree
// crowd score แสดงคู่ swarm — ไม่ป้อนกลับเข้า sim อัตโนมัติ

function VoteBar({ votes }: { votes: { agree: number; disagree: number } }) {
  const total = votes.agree + votes.disagree;
  const pctAgree = total ? (votes.agree / total) * 100 : 50;
  return (
    <div className="flex items-center gap-2 text-xs tabular-nums">
      <span className="text-primary-strong">👍 {votes.agree}</span>
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-red-200">
        <div className="h-full bg-primary" style={{ width: `${pctAgree}%` }} />
      </div>
      <span className="text-red-600">👎 {votes.disagree}</span>
    </div>
  );
}

export default function Gallery() {
  const { t } = useLang();
  const [items, setItems] = useState<GalleryListItem[]>([]);
  const [detail, setDetail] = useState<GalleryDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    fetchGallery()
      .then((i) => {
        setItems(i);
        setError("");
      })
      .catch((e) => setError(String(e.message ?? e)));
  useEffect(() => {
    load();
  }, []);

  const card = "bg-card border border-border rounded-2xl p-5";

  async function vote(token: string, v: "agree" | "disagree") {
    setBusy(true);
    try {
      const votes = await voteGallery(token, v);
      setItems((prev) => prev.map((i) => (i.share_token === token ? { ...i, votes } : i)));
      if (detail?.share_token === token) setDetail({ ...detail, votes });
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("gal_eyebrow")} title={t("gal_title")} desc={t("gal_sub")} />

      {/* Disclaimer ถาวร — GOV-03/CIT-04 */}
      <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-900">
        ⚠️ AI simulation — not a real poll | {t("gal_disclaimer")}
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-5 text-sm">{error}</div>}

      {detail ? (
        <div className={card + " space-y-4"}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-xs text-muted-foreground">
                {detail.created_at.slice(0, 10)} · {detail.agents} agents · {detail.watermark.note}
              </div>
              <h2 className="mt-1 font-display text-2xl font-semibold">{detail.subject}</h2>
            </div>
            <button onClick={() => setDetail(null)} className="text-sm text-muted-foreground hover:text-foreground">
              ← {t("gal_back")}
            </button>
          </div>
          <ul className="space-y-1.5 text-sm">
            {(detail.payload.brief?.lines ?? []).map((ln: any, i: number) => (
              <li key={i} className={ln.kind === "risk" ? "text-red-700" : "text-primary-strong"}>
                {ln.kind === "risk" ? "⚠️" : "✅"} {ln.text}
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">
            Fragility {detail.payload.brief?.fragility_index}/100 — {detail.payload.brief?.confidence_label}
          </p>
          {(detail.payload.scenarios ?? []).length > 0 && (
            <div className="space-y-1.5">
              {Object.entries(detail.payload.scenarios[detail.payload.scenarios.length - 1].belief_by_segment as Record<string, number>).map(
                ([seg, v]) => (
                  <div key={seg} className="flex items-center gap-2 text-xs">
                    <span className="w-40 shrink-0 truncate text-muted-foreground">{seg}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary">
                      <div className="h-full bg-primary" style={{ width: `${v * 100}%` }} />
                    </div>
                    <span className="w-10 shrink-0 text-right tabular-nums">{pct(v)}</span>
                  </div>
                ),
              )}
            </div>
          )}
          <div className="flex items-center justify-between border-t border-border pt-3">
            <div>
              <div className="text-xs text-muted-foreground">
                {t("gal_crowd")} <InfoTip text={t("tip_crowd")} />
              </div>
              <VoteBar votes={detail.votes} />
            </div>
            <div className="flex gap-2">
              <button
                disabled={busy}
                onClick={() => vote(detail.share_token, "agree")}
                className="rounded-xl border border-primary/40 px-4 py-2 text-sm text-primary-strong hover:bg-primary/5 disabled:opacity-40"
              >
                👍 {t("gal_agree")}
              </button>
              <button
                disabled={busy}
                onClick={() => vote(detail.share_token, "disagree")}
                className="rounded-xl border border-red-200 px-4 py-2 text-sm text-red-700 hover:bg-red-50 disabled:opacity-40"
              >
                👎 {t("gal_disagree")}
              </button>
            </div>
          </div>
        </div>
      ) : items.length === 0 ? (
        <p className="py-16 text-center text-sm text-muted-foreground">{t("gal_empty")}</p>
      ) : (
        <div className="space-y-3">
          {items.map((i) => (
            <button
              key={i.share_token}
              onClick={() => fetchGalleryDetail(i.share_token).then(setDetail).catch((e) => setError(String(e.message ?? e)))}
              className={card + " block w-full text-left hover:bg-muted/40 transition"}
            >
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-muted-foreground">
                    {i.created_at.slice(0, 10)} · {i.agents} agents
                  </div>
                  <div className="mt-0.5 font-medium">{i.subject}</div>
                  <div className="mt-1 text-xs text-muted-foreground line-clamp-1">
                    {i.brief?.lines?.[0]?.text ?? ""}
                  </div>
                </div>
                <VoteBar votes={i.votes} />
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
