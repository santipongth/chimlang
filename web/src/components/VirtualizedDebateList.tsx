import { UIEvent, useMemo, useState } from "react";
import { DebatePostItem } from "../api";
import { useLang } from "../i18n";

const ROW_HEIGHT = 132;
const VIEWPORT_HEIGHT = 520;
const OVERSCAN = 4;

export function VirtualizedDebateList({ posts }: { posts: DebatePostItem[] }) {
  const { lang } = useLang();
  const [scrollTop, setScrollTop] = useState(0);
  const window = useMemo(() => {
    const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
    const visible = Math.ceil(VIEWPORT_HEIGHT / ROW_HEIGHT) + OVERSCAN * 2;
    return { start, end: Math.min(posts.length, start + visible) };
  }, [posts.length, scrollTop]);
  const onScroll = (event: UIEvent<HTMLDivElement>) => setScrollTop(event.currentTarget.scrollTop);

  return (
    <div
      role="list"
      aria-label={lang === "th" ? `โพสต์ดีเบต ${posts.length} รายการ` : `${posts.length} debate posts`}
      className="mt-4 overflow-y-auto rounded-xl border border-border bg-background"
      style={{ height: VIEWPORT_HEIGHT }}
      onScroll={onScroll}
      data-testid="virtual-debate-list"
    >
      <div className="relative" style={{ height: posts.length * ROW_HEIGHT }}>
        {posts.slice(window.start, window.end).map((post, offset) => {
          const index = window.start + offset;
          return (
            <article
              role="listitem"
              aria-posinset={index + 1}
              aria-setsize={posts.length}
              key={`${post.round_no}-${post.agent_idx}-${post.move_id ?? index}`}
              data-testid="debate-post-row"
              className={`absolute left-2 right-2 rounded-xl border p-3 text-sm ${post.failed ? "border-dashed border-border opacity-50" : "border-border bg-card"}`}
              style={{ top: index * ROW_HEIGHT + 6, height: ROW_HEIGHT - 10 }}
            >
              <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <span className="flex min-w-0 flex-wrap items-center gap-2 font-medium text-foreground">
                  <span className="truncate">{post.segment}</span>
                  <span className="rounded-full border border-border px-2 py-0.5 text-[10px] text-muted-foreground">{post.move_type ?? (lang === "th" ? "คำกล่าวอ้างเดิม" : "legacy claim")}</span>
                  {post.move_id && <code className="text-[10px] text-muted-foreground">{post.move_id}</code>}
                </span>
                <span className="shrink-0 tabular-nums">{post.stance >= 0 ? "+" : ""}{post.stance.toFixed(2)}</span>
              </div>
              <p className="mt-1 line-clamp-2">{post.failed ? (lang === "th" ? `(คำตอบ agent ล้มเหลว: ${post.failure_reason ?? "ไม่ทราบสาเหตุ"})` : `(agent response failed: ${post.failure_reason ?? "unknown"})`) : post.content}</p>
              {!post.failed && (post.parent_move_id || (post.evidence_refs?.length ?? 0) > 0) && (
                <p className="mt-1 truncate text-[11px] text-muted-foreground">
                  {post.parent_move_id ? `↳ ${post.parent_move_id}` : ""}
                  {post.parent_move_id && post.evidence_refs?.length ? " · " : ""}
                  {post.evidence_refs?.length ? `evidence ${post.evidence_refs.join(", ")}` : ""}
                </p>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
