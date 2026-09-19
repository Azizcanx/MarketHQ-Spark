"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { MessageCircle, Send, X } from "lucide-react";

type Message = { role: "user" | "assistant"; content: string; at: string };
type Preflight = { enabled: boolean; configured: boolean; reachable: boolean; model: string | null; error: string | null };
type HermesManagerDockProps = { fullPage?: boolean };

const starterMessages: Message[] = [{ role: "assistant", content: "Hermes hazır. MarketHQ'yu yönetmek için normal konuşma dili kullan. Araştırma başlatmamı, durumu incelememi veya kontrollü bir işi ekibe vermemi söyle.", at: "0" }];

function getSessionId() {
  const key = "markethq.hermes.manager.session";
  const current = window.localStorage.getItem(key);
  if (current) return current;
  const next = `manager-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
  window.localStorage.setItem(key, next);
  return next;
}

export function HermesManagerDock({ fullPage = false }: HermesManagerDockProps) {
  const pathname = usePathname();
  const [open, setOpen] = useState(fullPage);
  const [messages, setMessages] = useState<Message[]>(starterMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => { if (fullPage) setOpen(true); }, [fullPage]);

  useEffect(() => {
    let mounted = true;
    const refresh = async () => {
      try {
        const response = await fetch("/api/hermes/chat", { cache: "no-store" });
        const data = await response.json();
        if (mounted) setPreflight(data.preflight ?? null);
      } catch {
        if (mounted) setPreflight(null);
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 10000);
    return () => { mounted = false; window.clearInterval(timer); };
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, sending]);

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const message = input.trim();
    if (!message || sending) return;
    setInput("");
    setError(null);
    setMessages((current) => [...current, { role: "user", content: message, at: new Date().toISOString() }]);
    setSending(true);
    try {
      const response = await fetch("/api/hermes/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ message, sessionId: getSessionId() }),
        cache: "no-store",
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.success !== true) throw new Error(data.error ?? `Hermes HTTP ${response.status}`);
      setMessages((current) => [...current, { role: "assistant", content: String(data.reply ?? "Hermes yanıt vermedi."), at: new Date().toISOString() }]);
      if (data.preflight) setPreflight(data.preflight);
    } catch (err) {
      const text = err instanceof Error ? err.message : "Hermes isteği başarısız oldu.";
      setError(text);
      setMessages((current) => [...current, { role: "assistant", content: `Hermes bağlantısı başarısız: ${text}`, at: new Date().toISOString() }]);
    } finally { setSending(false); }
  }

  if (!fullPage && pathname === "/hermes") return null;

  const online = preflight?.reachable === true;
  const panel = (
    <section className={fullPage ? "flex min-h-[calc(100vh-4rem)] flex-1 flex-col overflow-hidden bg-[#0d0a07] text-[#f2eee9]" : "fixed bottom-5 right-5 z-50 flex h-[min(720px,calc(100vh-2rem))] w-[min(560px,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-[#3a2a20] bg-[#0d0a07] text-[#f2eee9] shadow-[0_24px_80px_rgba(0,0,0,0.55)]"}>
      <header className="flex items-center justify-between border-b border-[#2b2019] bg-[#120e0b] px-4 py-3 font-mono text-xs">
        <div className="flex min-w-0 items-center gap-3">
          <span className="font-bold tracking-[0.18em] text-[#f28a42]">HERMES</span>
          <span className={online ? "text-[#7ee787]" : "text-[#9b8d83]"}>● {online ? "online" : "standby"}</span>
          <span className="hidden truncate text-[#776a61] sm:inline">MarketHQ manager</span>
        </div>
        {!fullPage && <button type="button" onClick={() => setOpen(false)} className="rounded-md p-1 text-[#a99a90] hover:bg-[#1b1511] hover:text-white" aria-label="Kapat"><X className="h-4 w-4" /></button>}
      </header>
      <div className="flex-1 overflow-y-auto px-4 py-4 font-mono text-[13px] leading-6 sm:px-6">
        <div className="mb-5 text-[#776a61]">MarketHQ Agent OS · research-only control channel</div>
        {messages.map((message, index) => (
          <div key={`${message.at}-${index}`} className="mb-5">
            <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.16em] text-[#806f63]">{message.role === "user" ? "owner" : "hermes"}</div>
            <div className="whitespace-pre-wrap break-words">
              {message.role === "user" ? <span className="text-[#f28a42]">❯ </span> : <span className="text-[#7ee787]">› </span>}
              <span className={message.role === "user" ? "text-[#f5e9df]" : "text-[#ddd3cb]"}>{message.content}</span>
            </div>
          </div>
        ))}
        {sending && <div className="mb-5 text-[#8b7b70]"><span className="text-[#f28a42]">› </span>Hermes düşünüyor ve uygun akışı hazırlıyor…</div>}
        <div ref={endRef} />
      </div>
      <form onSubmit={sendMessage} className="border-t border-[#2b2019] bg-[#100c09]">
        {error && <div className="border-b border-[#4a2822] bg-[#1a0f0c] px-4 py-2 font-mono text-[11px] text-[#ff9b8d]">{error}</div>}
        <div className="flex items-end gap-3 px-4 py-3 sm:px-5">
          <span className="pb-3 font-mono text-lg text-[#f28a42]">❯</span>
          <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder="Hermes'e bir görev ver…" rows={2} className="min-h-14 flex-1 resize-none bg-transparent font-mono text-[13px] text-[#f2eee9] outline-none placeholder:text-[#5f534b]" />
          <button type="submit" disabled={sending || !input.trim()} className="rounded-lg border border-[#3b2a21] bg-[#17110d] p-3 text-[#f28a42] transition hover:border-[#6a4734] hover:bg-[#1d1510] disabled:cursor-not-allowed disabled:opacity-30" aria-label="Gönder"><Send className="h-4 w-4" /></button>
        </div>
        <div className="flex items-center justify-between border-t border-[#201712] px-4 py-2 font-mono text-[10px] text-[#65584f] sm:px-5">
          <span>Enter gönder · Shift+Enter yeni satır</span>
          <span>{preflight?.model ?? "hermes-agent"}</span>
        </div>
      </form>
    </section>
  );

  if (fullPage) return panel;
  return (
    <>
      {open && panel}
      {!open && <button type="button" onClick={() => setOpen(true)} className="fixed bottom-5 right-5 z-50 flex items-center gap-2 rounded-xl border border-[#4b3427] bg-[#0d0a07] px-4 py-3 font-mono text-xs font-bold tracking-[0.12em] text-[#f28a42] shadow-[0_14px_40px_rgba(0,0,0,0.35)] transition hover:-translate-y-0.5 hover:border-[#6e4b36]"><MessageCircle className="h-4 w-4" />HERMES</button>}
    </>
  );
}
