"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Clock,
  FileCode,
  FileText,
  Play,
  RefreshCw,
  Sparkles,
  Terminal as TerminalIcon,
  Cpu,
  Activity,
  Archive,
} from "lucide-react";

import {
  DemoBadge,
  ErrorCard,
  LoadingRow,
  StoreNav,
  StoreShell,
  useStoreStatus,
} from "../_components";

interface AgentPreset {
  id: string;
  title: string;
  description: string;
  task: string;
  icon: string;
}

const PRESETS: AgentPreset[] = [
  {
    id: "stock-forecast",
    title: "📦 Stok & Talep Tahmini",
    description: "Kritik seviyedeki stokları inceleyip sipariş hızına göre tükenme riskini raporlar.",
    task: "Trendyol mağaza envanterindeki kritik ve tükenen stokları analiz et, acil tedarik önerilerini listele.",
    icon: "📦",
  },
  {
    id: "margin-audit",
    title: "💰 Fiyat & Kâr Marjı Denetimi",
    description: "Ürün bazında komisyon, kargo ve maliyet düşüldükten sonraki kârlılık durumunu değerlendir.",
    task: "Mağazadaki ürün fiyatlarını, tahmini %18 komisyon ve kargo giderlerini dikkate alarak kârlılık optimizasyonu yap.",
    icon: "💰",
  },
  {
    id: "returns-analysis",
    title: "🔄 İade & Sipariş Kalite Raporu",
    description: "İade edilen siparişleri ve olası iade nedenlerini özetleyip aksiyon planı çıkarır.",
    task: "Son siparişlerdeki iade ve iptal oranlarını değerlendir ve paketleme/ürün kalitesi iyileştirme adımlarını sun.",
    icon: "🔄",
  },
  {
    id: "research-backtest",
    title: "📈 THYAO.IS 1h Araştırma & Backtest",
    description: "MarketHQ Quant Research motorunu çalıştırıp setup ve backtest kartı üretir.",
    task: "research THYAO.IS 1h --backtest",
    icon: "📈",
  },
];

interface Session {
  title: string;
  id: string;
  lastActive: string;
}

// ── Pixel-border box ──
function PixelBox({
  children,
  className = "",
  accent = "primary",
}: {
  children: React.ReactNode;
  className?: string;
  accent?: "primary" | "amber" | "emerald" | "rose" | "blue";
}) {
  const accentClass =
    accent === "primary"
      ? "border-primary/60 shadow-primary/10"
      : accent === "amber"
        ? "border-amber-500/60 shadow-amber-500/10"
        : accent === "emerald"
          ? "border-emerald-500/60 shadow-emerald-500/10"
          : accent === "rose"
            ? "border-rose-500/60 shadow-rose-500/10"
            : "border-blue-500/60 shadow-blue-500/10";

  return (
    <div
      className={`relative rounded-sm border border-border bg-card shadow-lg ${accentClass} ${className}`}
    >
      <div className="absolute -top-px -left-px w-3 h-3 border-t-2 border-l-2 border-primary/40 rounded-tl-sm" />
      <div className="absolute -top-px -right-px w-3 h-3 border-t-2 border-r-2 border-primary/40 rounded-tr-sm" />
      <div className="absolute -bottom-px -left-px w-3 h-3 border-b-2 border-l-2 border-primary/40 rounded-bl-sm" />
      <div className="absolute -bottom-px -right-px w-3 h-3 border-b-2 border-r-2 border-primary/40 rounded-br-sm" />
      {children}
    </div>
  );
}

// ── Scanline terminal ──
function ScanlineTerminal({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`relative overflow-hidden ${className}`}>
      <div
        className="pointer-events-none absolute inset-0 z-10"
        style={{
          background:
            "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.06) 2px, rgba(0,0,0,0.06) 4px)",
        }}
      />
      <div
        className="absolute inset-0 z-0 opacity-30"
        style={{
          background:
            "radial-gradient(ellipse at 50% 0%, rgba(56,189,248,0.08) 0%, transparent 70%)",
        }}
      />
      <div className="relative z-10">{children}</div>
    </div>
  );
}

// ── Agent desk ──
function AgentDesk({
  name,
  role,
  status,
  task,
}: {
  name: string;
  role: string;
  status: "idle" | "running" | "done" | "error";
  task?: string;
}) {
  const statusColors = {
    idle: "border-muted-foreground/30 bg-muted/20",
    running: "border-amber-500/60 bg-amber-500/5 shadow-lg shadow-amber-500/10",
    done: "border-emerald-500/60 bg-emerald-500/5",
    error: "border-rose-500/60 bg-rose-500/5",
  };
  const statusIcon = {
    idle: <Clock className="h-3 w-3 text-muted-foreground" />,
    running: <RefreshCw className="h-3 w-3 animate-spin text-amber-400" />,
    done: <CheckCircle2 className="h-3 w-3 text-emerald-400" />,
    error: <AlertCircle className="h-3 w-3 text-rose-400" />,
  };

  return (
    <div className={`rounded-sm border p-3 transition-all duration-300 ${statusColors[status]}`}>
      <div className="flex items-center gap-2 mb-2">
        <div className="h-6 w-6 rounded-sm bg-background flex items-center justify-center text-xs">🤖</div>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-bold truncate">{name}</div>
          <div className="text-[10px] text-muted-foreground truncate">{role}</div>
        </div>
        {statusIcon[status]}
      </div>
      {task && (
        <div className="text-[10px] text-muted-foreground/70 truncate mt-1 font-mono">{task}</div>
      )}
      {status === "running" && (
        <div className="mt-2 h-1 rounded-full bg-muted overflow-hidden">
          <div className="h-full bg-amber-400 animate-pulse rounded-full" style={{ width: "60%" }} />
        </div>
      )}
    </div>
  );
}

// ── Session card ──
function SessionCard({
  session,
  onResume,
}: {
  session: Session;
  onResume: (id: string, title: string) => void;
}) {
  return (
    <div className="flex items-center justify-between rounded-sm border border-border bg-card/50 px-3 py-2 hover:bg-card transition-colors">
      <div className="min-w-0">
        <div className="text-xs font-medium truncate">{session.title}</div>
        <div className="text-[10px] text-muted-foreground">{session.lastActive}</div>
      </div>
      <button
        type="button"
        onClick={() => onResume(session.id, session.title)}
        className="shrink-0 rounded px-2 py-1 text-[10px] font-bold text-primary hover:bg-primary/10 transition-colors"
      >
        Devam Et
      </button>
    </div>
  );
}

// ── Main page ──
export default function AgentSpacePage() {
  const status = useStoreStatus();
  const [taskInput, setTaskInput] = useState("");
  const [running, setRunning] = useState(false);
  const [autonomousGoal, setAutonomousGoal] = useState("");
  const [autonomousRunning, setAutonomousRunning] = useState(false);
  const [autonomousResult, setAutonomousResult] = useState<any>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [runStatus, setRunStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [runResult, setRunResult] = useState<Record<string, unknown> | null>(null);
  const [activeTab, setActiveTab] = useState<"terminal" | "evidence" | "testcard">("terminal");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [showSessions, setShowSessions] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);

  const loadSessions = async () => {
    try {
      const res = await fetch("/api/agentspace/sessions", {
        headers: { Authorization: "Bearer markethq-agentspace-1789732782" },
      });
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);
      }
    } catch { /* ignore */ }
  };

  useEffect(() => { loadSessions(); }, []);

  const resumeSession = (sessionId: string, title: string) => {
    setTaskInput(`--resume ${sessionId} ${title}`);
    setShowSessions(false);
  };

  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  const runAgentTask = async (taskToRun: string) => {
    if (!taskToRun.trim() || running) return;
    setRunning(true);
    setRunStatus("running");
    setLogs(["[START] Görev başlatılıyor: \"" + taskToRun + '"']);
    setRunResult(null);

    try {
      const res = await fetch("/api/agentspace/run", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer markethq-agentspace-1789732782",
        },
        body: JSON.stringify({ task: taskToRun }),
      });

      const data = await res.json();
      if (!res.ok || data.success === false) {
        throw new Error(data.error || "Görev yürütülemedi");
      }

      const runId = data.id;

      const evtSource = new EventSource(
        `/api/agentspace/stream?task=${encodeURIComponent(taskToRun)}`
      );
      const liveLogs: string[] = [];

      evtSource.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (msg.kind === "stdout") {
            liveLogs.push(msg.line);
            setLogs([...liveLogs]);
          } else if (msg.kind === "stderr") {
            liveLogs.push("[ERR] " + msg.line);
            setLogs([...liveLogs]);
          } else if (msg.kind === "done") {
            evtSource.close();
            clearTimeout(timeoutId);
            setRunning(false);
            setRunStatus("done");
            setRunResult({ exit_code: msg.exitCode, logs: liveLogs });
          } else if (msg.kind === "error") {
            evtSource.close();
            clearTimeout(timeoutId);
            setRunning(false);
            setRunStatus("error");
            setLogs((prev) => [...prev, "[ERROR] " + msg.message]);
          }
        } catch { /* ignore parse errors */ }
      };

      let timeoutId: NodeJS.Timeout;

      evtSource.onerror = () => {
        evtSource.close();
        clearTimeout(timeoutId);
        setRunning(false);
      };

      const pollInterval = setInterval(async () => {
        try {
          const pollRes = await fetch(`/api/agentspace/run?id=${runId}`, {
            headers: { Authorization: "Bearer markethq-agentspace-1789732782" },
          });
          if (!pollRes.ok) return;
          const p = await pollRes.json();
          if (!p.success) return;
          if (p.status === "done" || p.status === "error") {
            clearInterval(pollInterval);
            evtSource.close();
            clearTimeout(timeoutId);
            setRunning(false);
            setRunStatus(p.status);
            setRunResult(p.result || p);
            if (p.logs && p.logs.length > liveLogs.length) setLogs(p.logs);
          }
        } catch { /* ignore */ }
      }, 2000);

      timeoutId = setTimeout(() => {
        evtSource.close();
        setRunning(false);
        setRunStatus("error");
        setLogs((prev) => [...prev, "[WARN] Zaman aşımı - görev tamamlanmadı"]);
      }, 300000);
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Görev hatası";
      setLogs((prev) => [...prev, "[ERROR] " + errorMsg]);
      setRunStatus("error");
      setRunning(false);
    }
  };

  const runAutonomousGoal = async (goal: string) => {
    if (!goal.trim() || autonomousRunning) return;
    setAutonomousRunning(true);
    setAutonomousResult(null);
    setLogs((prev) => [...prev, "[GOAL] Otonom hedef başlatılıyor: \"" + goal + '\"']);

    try {
      const res = await fetch("/api/agentspace/autonomous", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer markethq-agentspace-1789732782",
        },
        body: JSON.stringify({ goal }),
      });
      const data = await res.json();
      if (!res.ok || data.success === false) {
        throw new Error(data.error || "Hedef yürütülemedi");
      }
      setLogs((prev) => [...prev, "[GOAL] Sonuç: " + data.status + " (" + (data.successful || 0) + "/" + (data.total_tasks || 0) + ")"]);
      setAutonomousResult(data);
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Hedef hatası";
      setLogs((prev) => [...prev, "[GOAL] [ERROR] " + errorMsg]);
    } finally {
      setAutonomousRunning(false);
    }
  };

  return (
    <StoreShell
      crumb="MarketHQ / Intelligence"
      title="AgentSpace & AI Görev Merkezi"
      description="Hermes Agent ve MarketHQ deterministik zeka motorları ile canlı görev çalıştırma, log akışı ve kanıt üretimi."
    >
      <StoreNav />

      {status?.source === "mock" && (
        <div className="mt-4">
          <DemoBadge />
        </div>
      )}

      <div className="mt-6 space-y-6">
        {/* ── Hero header ── */}
        <PixelBox className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-primary" />
                <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-primary">
                  AgentSpace
                </span>
              </div>
              <h2 className="mt-1 text-xl font-black tracking-tight">Yapay Zeka Ofisi</h2>
              <p className="mt-1 text-xs text-muted-foreground">Görev ver, ajansın çalışmasını izle, kanıt al.</p>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 rounded-sm border border-border bg-background px-3 py-1.5">
                <Cpu className="h-3.5 w-3.5 text-primary" />
                <span className="text-[10px] font-mono text-muted-foreground">
                  Hermes · inclusionai/ling-3.0-flash-sante:free
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
                <span className="text-[10px] font-bold text-emerald-400">BAĞLI</span>
              </div>
            </div>
          </div>
        </PixelBox>

        {/* ── Agent desks ── */}
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
            <Activity className="h-3.5 w-3.5 text-primary" /> Ajansız Ofis
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <AgentDesk
              name="Hermes"
              role="Ana Ajans"
              status={running ? "running" : "idle"}
              task={running ? taskInput : undefined}
            />
            <AgentDesk name="Research" role="Veri Analiz" status="idle" />
            <AgentDesk name="Quant" role="Backtest Motoru" status="idle" />
            <AgentDesk name="Trader" role="Sinyal Üretici" status="idle" />
          </div>
        </div>

        {/* ── Quick task presets ── */}
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5 text-primary" /> Hızlı Görevler
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => {
                  setTaskInput(preset.task);
                  void runAgentTask(preset.task);
                }}
                disabled={running}
                className="group relative flex flex-col justify-between rounded-sm border border-border bg-card p-4 text-left transition hover:border-primary/50 hover:shadow-sm hover:shadow-primary/10 disabled:opacity-50"
              >
                <div>
                  <div className="text-sm font-bold text-foreground group-hover:text-primary">
                    {preset.title}
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                    {preset.description}
                  </p>
                </div>
                <div className="mt-3 flex items-center gap-1.5 text-[11px] font-semibold text-primary">
                  <Play className="h-3 w-3" /> Çalıştır
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* ── Task input ── */}
        <PixelBox className="p-5">
          <div className="flex items-center gap-2 text-sm font-bold text-foreground">
            <Bot className="h-4 w-4 text-primary" /> Özel Görev veya Araştırma Prompt&apos;u
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Hermes Agent terminalde çalışacak, çıktıları anlık olarak altta akıtacak ve kanıt kartı üretecektir.
          </p>

          {sessions.length > 0 && (
            <div className="mt-3 relative">
              <button
                type="button"
                onClick={() => setShowSessions(!showSessions)}
                className="flex items-center gap-2 rounded-sm border border-border bg-muted/20 px-3 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-muted/40"
              >
                <Archive className="h-3 w-3" /> Geçmiş Sessions ({sessions.length})
              </button>
              {showSessions && (
                <div className="absolute z-10 mt-1 w-full max-w-lg rounded-sm border border-border bg-background shadow-lg">
                  {sessions.map((s) => (
                    <SessionCard key={s.id} session={s} onResume={resumeSession} />
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <input
              type="text"
              value={taskInput}
              onChange={(e) => setTaskInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !running) {
                  void runAgentTask(taskInput);
                }
              }}
              placeholder="Örn: Trendyol mağaza sipariş özetini ve iade oranlarını raporla..."
              disabled={running}
              className="flex-1 rounded-sm border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
            <button
              type="button"
              onClick={() => void runAgentTask(taskInput)}
              disabled={running || !taskInput.trim()}
              className="inline-flex items-center justify-center gap-2 rounded-sm bg-primary px-5 py-2.5 text-sm font-bold text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
            >
              {running ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" /> Çalışıyor…
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" /> Başlat
                </>
              )}
            </button>
          </div>

          {/* Autonomous Goal */}
          <div className="mt-3 rounded-sm border border-amber-500/30 bg-amber-500/5 p-3">
            <div className="mb-2 flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-amber-400" />
              <span className="text-sm font-bold text-amber-400">Otonom Hedef</span>
              <span className="text-xs text-muted-foreground">— Sistem kendini geliştirir</span>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                type="text"
                value={autonomousGoal}
                onChange={(e) => setAutonomousGoal(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !autonomousRunning) {
                    void runAutonomousGoal(autonomousGoal);
                  }
                }}
                placeholder="Örn: Trendyol sipariş analiz et ve rapor oluştur"
                disabled={autonomousRunning}
                className="flex-1 rounded-sm border border-amber-500/30 bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-amber-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => void runAutonomousGoal(autonomousGoal)}
                disabled={autonomousRunning || !autonomousGoal.trim()}
                className="inline-flex items-center justify-center gap-2 rounded-sm bg-amber-500 px-5 py-2.5 text-sm font-bold text-amber-950 transition hover:opacity-90 disabled:opacity-50"
              >
                {autonomousRunning ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" /> Çalışıyor…
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4" /> Otonom Başlat
                  </>
                )}
              </button>
            </div>
            {autonomousResult && (
              <div className="mt-2 rounded-sm bg-background/50 p-2 text-xs text-muted-foreground">
                Status: {autonomousResult.status} | Successful: {autonomousResult.successful}/{autonomousResult.total_tasks}
              </div>
            )}
          </div>
        </PixelBox>

        {/* ── Terminal output ── */}
        <PixelBox accent="amber" className="p-0 overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/40 px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="flex gap-1.5">
                <span className="h-3 w-3 rounded-full bg-rose-500/80" />
                <span className="h-3 w-3 rounded-full bg-amber-500/80" />
                <span className="h-3 w-3 rounded-full bg-emerald-500/80" />
              </div>
              <span className="ml-2 font-mono text-xs font-semibold text-muted-foreground">
                hermes-terminal
              </span>
            </div>

            <div className="flex items-center gap-2">
              {runStatus === "running" && (
                <span className="flex items-center gap-1.5 rounded-full bg-amber-500/10 px-2.5 py-0.5 font-mono text-[11px] font-bold text-amber-400">
                  <span className="h-2 w-2 animate-ping rounded-full bg-amber-400" /> CANLI
                </span>
              )}
              {runStatus === "done" && (
                <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-0.5 font-mono text-[11px] font-bold text-emerald-400">
                  <CheckCircle2 className="h-3 w-3" /> TAMAMLANDI
                </span>
              )}
              {runStatus === "error" && (
                <span className="flex items-center gap-1.5 rounded-full bg-rose-500/10 px-2.5 py-0.5 font-mono text-[11px] font-bold text-rose-400">
                  <AlertCircle className="h-3 w-3" /> HATA
                </span>
              )}

              <div className="flex rounded-sm border border-border/60 bg-muted/20 p-0.5">
                {[
                  { key: "terminal", icon: TerminalIcon, label: "Terminal" },
                  { key: "evidence", icon: FileCode, label: "Evidence" },
                  { key: "testcard", icon: FileText, label: "Test Card" },
                ].map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => setActiveTab(tab.key as typeof activeTab)}
                    className={`flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition ${
                      activeTab === tab.key
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <tab.icon className="h-3 w-3" /> {tab.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="mt-0">
            {activeTab === "terminal" && (
              <ScanlineTerminal className="h-80 overflow-y-auto bg-black/90 p-4 font-mono text-xs leading-relaxed text-[#58d68d]">
                {logs.length === 0 ? (
                  <div className="text-muted-foreground/60 italic">
                    Terminal hazır. Yukarıdan bir görev seçin veya bir prompt girip &quot;Başlat&quot;a basın.
                  </div>
                ) : (
                  logs.map((log, idx) => (
                    <div key={idx} className="whitespace-pre-wrap break-all py-0.5">
                      {log}
                    </div>
                  ))
                )}
              </ScanlineTerminal>
            )}

            {activeTab === "evidence" && runResult && (
              <div className="h-80 overflow-y-auto bg-black/90 p-4 font-mono text-xs text-blue-300">
                <pre>{JSON.stringify(runResult, null, 2)}</pre>
              </div>
            )}

            {activeTab === "testcard" && runResult && (
              <div className="h-80 overflow-y-auto bg-black/90 p-4 text-xs text-slate-200">
                <div className="rounded-sm border border-border/40 bg-card/40 p-4">
                  <div className="font-bold text-primary">Görev Özeti:</div>
                  <p className="mt-1 text-muted-foreground">{taskInput}</p>
                  <div className="mt-3 font-bold text-foreground">Durum & Metrikler:</div>
                  <pre className="mt-1 font-mono text-[11px] text-emerald-400">
                    Exit Code: {String(runResult.exit_code ?? 0)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </PixelBox>
      </div>
    </StoreShell>
  );
}