import React, { useState, useEffect } from 'react';
import {
  X,
  Cpu,
  HardDrive,
  Activity,
  Wifi,
  RotateCw,
  Trash2,
  Download,
  CheckCircle2,
  Server,
  Zap,
  Terminal,
  Clock,
  Sparkles
} from 'lucide-react';

interface PerformanceDashboardModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface ProcessItem {
  id: string;
  name: string;
  pid: number;
  cpu: number;
  memoryMb: number;
  status: 'running' | 'idle' | 'standby';
  threads: number;
  detail: string;
}

export const PerformanceDashboardModal: React.FC<PerformanceDashboardModalProps> = ({
  isOpen,
  onClose,
}) => {
  // Live simulated metrics with dynamic jitter
  const [cpuUsage, setCpuUsage] = useState(18.2);
  const [memoryUsageMb, setMemoryUsageMb] = useState(312);
  const [totalMemoryMb] = useState(1024);
  const [networkDownKb, setNetworkDownKb] = useState(48.6);
  const [networkUpKb, setNetworkUpKb] = useState(14.2);
  const [rpcLatencyMs, setRpcLatencyMs] = useState(12);
  const [historyCpu, setHistoryCpu] = useState<number[]>([
    14, 16, 22, 19, 15, 18, 24, 20, 17, 19, 21, 18, 16, 20, 18,
  ]);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  const [processes, setProcesses] = useState<ProcessItem[]>([
    {
      id: 'p-1',
      name: 'Aetherius IDE Core Server',
      pid: 1024,
      cpu: 4.8,
      memoryMb: 94,
      status: 'running',
      threads: 4,
      detail: 'Vite SPA Ingress & WebSockets',
    },
    {
      id: 'p-2',
      name: 'TypeScript Language Server (TSServer)',
      pid: 1088,
      cpu: 6.2,
      memoryMb: 76,
      status: 'running',
      threads: 2,
      detail: 'AST Analysis & Type Checking',
    },
    {
      id: 'p-3',
      name: 'Vite 6 Dev Server Engine',
      pid: 1120,
      cpu: 2.1,
      memoryMb: 52,
      status: 'running',
      threads: 2,
      detail: 'Serving Port 3000 Ingress',
    },
    {
      id: 'p-4',
      name: 'Antigravity Agent Worker',
      pid: 1152,
      cpu: 4.4,
      memoryMb: 82,
      status: 'idle',
      threads: 3,
      detail: 'Gemini AI Background Dispatcher',
    },
    {
      id: 'p-5',
      name: 'Terminal PTY Shell Daemon',
      pid: 1204,
      cpu: 0.7,
      memoryMb: 18,
      status: 'standby',
      threads: 1,
      detail: 'bash virtual terminal session',
    },
  ]);

  // Periodic heartbeat animation
  useEffect(() => {
    if (!isOpen) return;

    const interval = setInterval(() => {
      const cpuDelta = (Math.random() - 0.48) * 3;
      const newCpu = Math.max(8, Math.min(65, +(cpuUsage + cpuDelta).toFixed(1)));
      setCpuUsage(newCpu);

      setHistoryCpu((prev) => [...prev.slice(1), newCpu]);

      const memDelta = Math.floor((Math.random() - 0.48) * 6);
      setMemoryUsageMb((prev) => Math.max(220, Math.min(780, prev + memDelta)));

      setNetworkDownKb(+(30 + Math.random() * 35).toFixed(1));
      setNetworkUpKb(+(8 + Math.random() * 15).toFixed(1));
      setRpcLatencyMs(Math.floor(9 + Math.random() * 8));

      // slight jitter in processes
      setProcesses((prev) =>
        prev.map((p) => ({
          ...p,
          cpu: +(Math.max(0.2, p.cpu + (Math.random() - 0.5) * 0.8)).toFixed(1),
        }))
      );
    }, 1800);

    return () => clearInterval(interval);
  }, [isOpen, cpuUsage]);

  if (!isOpen) return null;

  const handleGC = () => {
    setActionNotice('Running V8 Garbage Collection...');
    setTimeout(() => {
      setMemoryUsageMb((prev) => Math.max(210, prev - 68));
      setActionNotice('Freed 68 MB heap space. Memory compacted.');
      setTimeout(() => setActionNotice(null), 3000);
    }, 600);
  };

  const handleClearCache = () => {
    setActionNotice('Purging build artifacts & module cache...');
    setTimeout(() => {
      setActionNotice('Vite & TypeScript cache cleared successfully.');
      setTimeout(() => setActionNotice(null), 3000);
    }, 500);
  };

  const memPercent = Math.round((memoryUsageMb / totalMemoryMb) * 100);

  return (
    <div
      id="performance-dashboard-backdrop"
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 select-none animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        id="performance-dashboard-content"
        className="w-full max-w-4xl bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 flex items-center justify-center shadow-[0_0_15px_rgba(6,182,212,0.3)]">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white tracking-tight">
                  IDE Internal Telemetry & Performance
                </h2>
                <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 text-[10px] font-mono flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Live (1.8s)
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Visualizing runtime memory heap, CPU load, and internal daemon processes
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Action Notification banner */}
          {actionNotice && (
            <div className="p-2.5 rounded-xl bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 text-xs font-mono flex items-center gap-2 animate-in fade-in">
              <Sparkles className="w-4 h-4 text-cyan-400 shrink-0" />
              <span>{actionNotice}</span>
            </div>
          )}

          {/* 3 Main Metric Cards: CPU, Memory, Network */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* CPU Card */}
            <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 shadow-sm flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
                  <div className="flex items-center gap-1.5 font-semibold text-slate-300">
                    <Cpu className="w-4 h-4 text-cyan-400" />
                    <span>CPU Utilization</span>
                  </div>
                  <span className="font-mono text-[11px] text-cyan-400">4 Cores</span>
                </div>
                <div className="flex items-baseline gap-2 mb-2">
                  <span className="text-3xl font-black text-white font-mono">{cpuUsage}%</span>
                  <span className="text-xs text-slate-400 font-mono">avg load</span>
                </div>
              </div>

              {/* Mini Sparkline Bars */}
              <div>
                <div className="h-10 flex items-end gap-1 mb-2 pt-2">
                  {historyCpu.map((val, idx) => (
                    <div
                      key={idx}
                      className="flex-1 bg-cyan-500/30 hover:bg-cyan-400 rounded-t transition-all"
                      style={{ height: `${Math.min(100, Math.max(10, val * 1.5))}%` }}
                      title={`${val}%`}
                    />
                  ))}
                </div>
                <div className="text-[10px] text-slate-500 flex justify-between font-mono">
                  <span>-30s</span>
                  <span>Now</span>
                </div>
              </div>
            </div>

            {/* Memory Card */}
            <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 shadow-sm flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
                  <div className="flex items-center gap-1.5 font-semibold text-slate-300">
                    <HardDrive className="w-4 h-4 text-blue-400" />
                    <span>Memory (Heap)</span>
                  </div>
                  <span className="font-mono text-[11px] text-blue-400">{memPercent}%</span>
                </div>
                <div className="flex items-baseline gap-2 mb-3">
                  <span className="text-3xl font-black text-white font-mono">
                    {memoryUsageMb}
                  </span>
                  <span className="text-xs text-slate-400 font-mono">/ {totalMemoryMb} MB</span>
                </div>
              </div>

              {/* Progress Bar */}
              <div>
                <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden mb-2">
                  <div
                    className="h-full bg-gradient-to-r from-blue-500 to-cyan-400 rounded-full transition-all duration-300"
                    style={{ width: `${memPercent}%` }}
                  />
                </div>
                <div className="text-[10px] text-slate-500 flex justify-between font-mono">
                  <span>RSS: 396 MB</span>
                  <span>Free: {totalMemoryMb - memoryUsageMb} MB</span>
                </div>
              </div>
            </div>

            {/* Network Card */}
            <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 shadow-sm flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
                  <div className="flex items-center gap-1.5 font-semibold text-slate-300">
                    <Wifi className="w-4 h-4 text-emerald-400" />
                    <span>Network & RPC</span>
                  </div>
                  <span className="font-mono text-[11px] text-emerald-400">{rpcLatencyMs}ms ping</span>
                </div>
                <div className="grid grid-cols-2 gap-2 my-1">
                  <div>
                    <div className="text-[10px] text-slate-500 font-mono">Down (In)</div>
                    <div className="text-lg font-bold text-slate-100 font-mono">
                      {networkDownKb} <span className="text-xs font-normal text-slate-400">KB/s</span>
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-slate-500 font-mono">Up (Out)</div>
                    <div className="text-lg font-bold text-slate-100 font-mono">
                      {networkUpKb} <span className="text-xs font-normal text-slate-400">KB/s</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="pt-2 border-t border-slate-800/60 text-[10px] text-slate-500 flex justify-between font-mono">
                <span>WebSockets: 2 active</span>
                <span>Protobuf v3 RPC</span>
              </div>
            </div>
          </div>

          {/* Internal Processes Table */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <Server className="w-3.5 h-3.5 text-cyan-400" />
                <span>Internal Daemons & Worker Threads ({processes.length})</span>
              </h3>

              {/* Quick actions */}
              <div className="flex items-center gap-2">
                <button
                  onClick={handleGC}
                  className="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[11px] text-slate-300 hover:text-cyan-300 flex items-center gap-1.5 transition-colors"
                  title="Run V8 Garbage Collection"
                >
                  <RotateCw className="w-3 h-3" />
                  <span>Trigger GC</span>
                </button>

                <button
                  onClick={handleClearCache}
                  className="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[11px] text-slate-300 hover:text-rose-300 flex items-center gap-1.5 transition-colors"
                  title="Clear Module & Build Cache"
                >
                  <Trash2 className="w-3 h-3" />
                  <span>Flush Cache</span>
                </button>
              </div>
            </div>

            <div className="border border-slate-800 rounded-xl overflow-hidden shadow-sm bg-slate-900/50">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 text-[11px]">
                  <tr>
                    <th className="py-2.5 px-4 font-medium">Process Name</th>
                    <th className="py-2.5 px-3 font-medium">PID</th>
                    <th className="py-2.5 px-3 font-medium">CPU</th>
                    <th className="py-2.5 px-3 font-medium">RAM</th>
                    <th className="py-2.5 px-3 font-medium">Status</th>
                    <th className="py-2.5 px-4 font-medium hidden sm:table-cell">Subsystem</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {processes.map((proc) => (
                    <tr key={proc.id} className="hover:bg-slate-800/40 transition-colors">
                      <td className="py-2.5 px-4 font-semibold text-slate-200 flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-cyan-400" />
                        <span>{proc.name}</span>
                      </td>
                      <td className="py-2.5 px-3 text-slate-400">{proc.pid}</td>
                      <td className="py-2.5 px-3 text-cyan-300 font-semibold">{proc.cpu}%</td>
                      <td className="py-2.5 px-3 text-slate-300">{proc.memoryMb} MB</td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-sans font-medium uppercase tracking-wider ${
                            proc.status === 'running'
                              ? 'bg-emerald-500/20 text-emerald-400'
                              : proc.status === 'idle'
                              ? 'bg-blue-500/20 text-blue-400'
                              : 'bg-slate-800 text-slate-400'
                          }`}
                        >
                          {proc.status}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 text-slate-500 hidden sm:table-cell truncate max-w-xs">
                        {proc.detail}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-950 flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center gap-2 font-mono text-[11px]">
            <span>Container: Linux (Cloud Run Sandboxed)</span>
            <span>•</span>
            <span className="text-cyan-400">Port: 3000 (Ingress Active)</span>
          </div>

          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white text-xs font-semibold transition-colors"
          >
            Close Dashboard
          </button>
        </div>
      </div>
    </div>
  );
};
