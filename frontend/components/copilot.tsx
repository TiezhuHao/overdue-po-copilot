"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../lib/client";
import type { CopilotResult, QueryContext } from "../lib/contracts";
import { errorText, label } from "../lib/presentation";
import { Badge, ErrorBox, Loading } from "./ui";
const questions = ["为什么这个 PO 超期？", "这个订单还需要多久消耗完？", "建议怎么处理？", "这个订单是否与囤料有关？"];
export function Copilot({ context, onResult }: { context: QueryContext; onResult: (result: CopilotResult) => void }) {
  const [text,setText] = useState(""), [busy,setBusy] = useState(false), [error,setError] = useState("");
  const [history,setHistory] = useState<{ question: string; result: CopilotResult }[]>([]);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!text.trim() || busy || active.current) return;
    const question = text.trim(); const abort = new AbortController(); active.current = abort; setBusy(true); setError("");
    try { const result = await api.query(context, question, abort.signal); if (!abort.signal.aborted) { setHistory(items => [...items, { question, result }]); setText(""); onResult(result); } }
    catch (e) { if (!abort.signal.aborted) setError(errorText(e)); }
    finally { if (!abort.signal.aborted) { active.current = null; setBusy(false); } }
  }
  return <aside className="copilot-panel" aria-label="Copilot 助手"><div className="copilot-heading"><span className="copilot-icon">✳</span><div><h2>采购 Copilot</h2><p>用中文追问，基于同一份证据回答</p></div><span className="dot" /></div><div className="context-pill">已关联当前订单 · {context.snapshot_date}</div><div className="chat-content" aria-live="polite">{!history.length && <div className="chat-welcome"><h3>从“为什么”到“怎么办”</h3><p>我会沿用当前订单和数据集，先读取指标、诊断和处置结果，再组织回答。</p><div className="shortcut-list">{questions.map(q => <button disabled={busy} key={q} onClick={() => setText(q)}>{q}<span>↗</span></button>)}</div><small>快捷问题不预设答案。无模型配置时，系统使用确定性回答。</small></div>}{history.map((entry,i) => <article className="exchange" key={i}><div className="user-question"><small>你</small><p>{entry.question}</p></div><div className="assistant-answer"><div className="answer-meta"><span>COPILOT</span><span>{entry.result.answer_source === "MODEL" ? "证据校验通过" : entry.result.answer_source === "FALLBACK" ? "确定性回答" : "请补充信息"}</span></div><Badge code={entry.result.status} /><div className="answer-text">{entry.result.answer.split("\n").map((line,k) => line.startsWith("### ") ? <h4 key={k}>{line.slice(4)}</h4> : line ? <p key={k}>{line.startsWith("- ") ? line.slice(2) : line}</p> : null)}</div><details><summary>回答依据与限制 · {entry.result.evidence_references.length} 项引用</summary><ul>{entry.result.evidence_references.map(ref => <li key={ref.reference_id}>{ref.label} · {ref.version_date ?? ref.snapshot_date}</li>)}{entry.result.limitations.map((item,j) => <li key={j}>{label(item)}</li>)}</ul>{!!entry.result.candidate_schedule_ids.length && <p>匹配到多个发运行，请返回工作台选择准确记录后再分析。</p>}</details></div></article>)}{busy && <Loading text="正在读取证据并组织回答…" />}{error && <ErrorBox message={error} />}</div><form className="chat-form" onSubmit={submit}><label htmlFor="copilot-question">向当前订单提问</label><textarea id="copilot-question" placeholder="为什么这个 PO 超期？应该怎么办？" value={text} onChange={e => setText(e.target.value)} maxLength={2000} rows={3} disabled={busy} /><div><small>{text.length}/2000 · 仅本页临时记录</small><button className="primary" disabled={busy || !text.trim()}>{busy ? "分析中…" : "发送问题 ↑"}</button></div></form><p className="copilot-disclaimer">不会执行采购操作，也不会补猜缺失证据。</p></aside>;
}
