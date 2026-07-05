import { createContext, useContext, useEffect, useState } from "react";

// i18n เบา (NFR-09): TH เป็นหลัก สลับ EN ได้ทุกหน้า — จำค่าไว้ใน localStorage
export type Lang = "th" | "en";

const DICT: Record<string, { th: string; en: string }> = {
  tagline: { th: "สนามซ้อมอนาคตของสังคมไทย", en: "Rehearse the future of Thai society" },
  watermark: {
    th: "AI simulation — not a real poll | ทุกตัวเลขเป็นผลจำลอง ไม่ใช่โพลจริง และไม่ใช่คำสัญญาของหน่วยงานใด",
    en: "AI simulation — not a real poll. All figures are simulation estimates, not real polling or promises.",
  },
  nav_home: { th: "หน้าแรก", en: "Home" },
  nav_new_run: { th: "รันใหม่", en: "New run" },
  nav_dashboard: { th: "แดชบอร์ดผู้บริหาร", en: "Executive Dashboard" },
  nav_citizen: { th: "โหมดประชาชน", en: "Citizen Mode" },
  nav_runs: { th: "การจัดการรัน", en: "Run History" },
  // Landing
  landing_eyebrow: { th: "DIGITAL SANDBOX", en: "DIGITAL SANDBOX" },
  landing_title: { th: "ซ้อมอนาคต ก่อนตัดสินใจจริง", en: "Rehearse the future before you decide" },
  landing_sub: {
    th: "จำลองปฏิกิริยาของสังคมไทยต่อนโยบาย แคมเปญ หรือคำแถลง — พร้อมพิสูจน์ความแม่นของตัวเองด้วย hindcast, fragility และ calibration",
    en: "Simulate Thai society's reaction to policies, campaigns and statements — with self-proving accuracy via hindcast, fragility and calibration.",
  },
  landing_cta: { th: "เริ่มรันแรกของคุณ", en: "Start your first run" },
  feat1_t: { th: "พิสูจน์ตัวเองได้", en: "Self-proving" },
  feat1_d: {
    th: "ทุกคำทำนายถูกบันทึกแบบแก้ไม่ได้ แล้ววัดผลจริงด้วย Brier score — เผยแพร่ทั้งผ่านและไม่ผ่าน",
    en: "Every prediction is registered immutably and scored against reality — published pass or fail.",
  },
  feat2_t: { th: "สังคมไทยจริง", en: "Thai social fabric" },
  feat2_d: {
    th: "กลุ่ม LINE ปิด, ฟีดสาธารณะ, ปากต่อปาก + เกรงใจ/say-do gap/ประชด เป็นพารามิเตอร์จริงของ agent",
    en: "Closed LINE groups, public feeds, word-of-mouth + kreng-jai, say-do gap and sarcasm as real agent parameters.",
  },
  feat3_t: { th: "ธรรมาภิบาลในโค้ด", en: "Governance by architecture" },
  feat3_d: {
    th: "PII ถูก block, election mode บังคับ aggregate, ทุก export มี watermark — บังคับที่ระดับโค้ด ไม่ใช่นโยบายกระดาษ",
    en: "PII blocked, election mode aggregate-only, every export watermarked — enforced in code, not on paper.",
  },
  // Wizard
  wiz_eyebrow: { th: "รันใหม่", en: "NEW RUN" },
  wiz_title: { th: "ออกแบบรันของคุณ", en: "Design your run" },
  wiz_step1: { th: "คำถาม", en: "Question" },
  wiz_step2: { th: "เครื่องยนต์", en: "Engine" },
  wiz_step3: { th: "ยืนยัน & รัน", en: "Review & Run" },
  wiz_q_label: { th: "คำถาม / หัวข้อ SCENARIO", en: "QUESTION / SCENARIO" },
  wiz_q_ph: { th: "จะเกิดอะไรถ้า...", en: "What if..." },
  wiz_domain: { th: "โดเมน", en: "DOMAIN" },
  wiz_agents: { th: "จำนวน agents", en: "Agents" },
  wiz_agents_note: {
    th: "มากขึ้น = เสถียรขึ้นแต่ช้าลง (cap 1,000/run — ระดับ 5,000 ต้องขออนุมัติ)",
    en: "More = steadier but slower (cap 1,000/run — 5,000 tier requires approval)",
  },
  wiz_universes: { th: "ทุกรันใช้ 5 จักรวาลคู่ขนานเพื่อวัด Fragility เสมอ", en: "Every run uses 5 parallel universes to measure fragility" },
  wiz_review: { th: "สรุปก่อนรัน", en: "Review before running" },
  wiz_election_warn: {
    th: "หัวข้อเกี่ยวกับเลือกตั้ง/การเมืองจะถูกบังคับ aggregate-only และปิด Sim-to-Signal โดยอัตโนมัติ (GOV-02)",
    en: "Election/political topics are forced aggregate-only with Sim-to-Signal disabled (GOV-02)",
  },
  back: { th: "← ย้อนกลับ", en: "← Back" },
  next: { th: "ถัดไป →", en: "Next →" },
  run_now: { th: "รันจำลอง →", en: "Run simulation →" },
  running: { th: "กำลังจำลอง...", en: "Simulating..." },
  // Dashboard
  dash_eyebrow: { th: "ผลจำลองล่าสุด", en: "LATEST RESULT" },
  dash_empty: { th: "ยังไม่มีผลรัน — เริ่มที่เมนู \"รันใหม่\"", en: "No results yet — start from \"New run\"" },
  brief_title: { th: "Executive Brief", en: "Executive Brief" },
  headline_range: { th: "ช่วงผลหลัก", en: "Headline range" },
  range_note: { th: "แสดงเป็นช่วงเสมอ ไม่มีตัวเลขเดี่ยว (TRUST-09)", en: "Always a range, never a point estimate (TRUST-09)" },
  compare_title: { th: "เปรียบเทียบ Scenario — สัดส่วนผู้เชื่อข่าวลือรายกลุ่ม", en: "Scenario comparison — rumor belief by segment" },
  pop_share: { th: "สัดส่วนประชากรต่อกลุ่ม", en: "Population share by segment" },
  pop_note: { th: "เสียงที่ปรากฏบนช่องทาง ≠ สัดส่วนคนจริง — อย่าอ่านเสียงดังแทนประชากร", en: "Voice share ≠ population share — don't read the loud as the many" },
  // Citizen
  cit_title: { th: "ครัวเรือนแบบฉัน (Personal Impact Twin)", en: "A household like mine (Personal Impact Twin)" },
  cit_sub: {
    th: "ตอบ 6 ข้อ (ตัวเลือกปิดทั้งหมด — เราไม่รับข้อความอิสระและไม่บันทึกคำตอบของคุณ: session-only)",
    en: "Answer 6 closed-choice questions — no free text, and your answers are never stored (session-only).",
  },
  cit_submit: { th: "ดูผลกระทบต่อครัวเรือนแบบฉัน", en: "See impact on households like mine" },
  cit_no_response: { th: "ถ้าไม่มีคำชี้แจงจากหน่วยงาน", en: "Without an official clarification" },
  cit_with_response: { th: "ถ้ามีคำชี้แจงชัดเจน", en: "With a clear clarification" },
  cit_worry: { th: "ของคนกลุ่มเดียวกับคุณกังวลเรื่องนี้", en: "of people like you are concerned" },
  cit_worry_after: { th: "ความกังวลลดลงเหลือประมาณนี้", en: "concern drops to roughly this" },
  cit_your_group: { th: "กลุ่มของคุณ", en: "Your segment" },
  cit_feedback: { th: "ร่วมส่งเสียงของคุณ (เปิดเผยเมื่อกลุ่มมีผู้ตอบครบ 20 คน — คุ้มครองตัวตน)", en: "Add your voice (published once your group reaches 20 responses — k-anonymity)" },
  f_income: { th: "ช่วงรายได้ต่อเดือน", en: "Monthly income band" },
  f_region: { th: "พื้นที่อยู่อาศัย", en: "Where you live" },
  f_commute: { th: "การเดินทางหลัก", en: "Main commute" },
  f_occupation: { th: "อาชีพ (แบบกว้าง)", en: "Occupation (broad)" },
  f_age: { th: "ช่วงอายุ", en: "Age band" },
  f_household: { th: "จำนวนสมาชิกครัวเรือน", en: "Household size" },
  // Runs
  runs_eyebrow: { th: "ประวัติ", en: "HISTORY" },
  runs_title: { th: "การจัดการรัน", en: "Run management" },
  runs_col_id: { th: "รัน", en: "Run" },
  runs_col_started: { th: "เริ่มเมื่อ", en: "Started" },
  runs_col_pred: { th: "คำทำนาย", en: "Predictions" },
  runs_col_export: { th: "Export", en: "Exported" },
  runs_due_title: { th: "คำทำนายที่ครบกำหนด (รอ resolve)", en: "Predictions due (awaiting resolution)" },
  runs_due_empty: { th: "ไม่มีคำทำนายค้าง resolve", en: "Nothing awaiting resolution" },
  runs_empty: { th: "ยังไม่มีรันในระบบ", en: "No runs yet" },
  runs_note: {
    th: "ทุกรันมี audit log แบบแก้ไม่ได้ + คำทำนายอย่างน้อย 1 รายการ — resolve ผ่าน scripts/resolve_predictions.py",
    en: "Every run has an immutable audit log and ≥1 registered prediction — resolve via scripts/resolve_predictions.py",
  },
  db_down: { th: "เชื่อมต่อฐานข้อมูลไม่ได้ (docker compose up -d)", en: "Database unavailable (docker compose up -d)" },
};

const LangCtx = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: (k: string) => string }>({
  lang: "th",
  setLang: () => {},
  t: (k) => k,
});

export function LangProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => (localStorage.getItem("chimlang-lang") as Lang) || "th");
  useEffect(() => localStorage.setItem("chimlang-lang", lang), [lang]);
  const t = (k: string) => DICT[k]?.[lang] ?? k;
  return <LangCtx.Provider value={{ lang, setLang, t }}>{children}</LangCtx.Provider>;
}

export const useLang = () => useContext(LangCtx);
