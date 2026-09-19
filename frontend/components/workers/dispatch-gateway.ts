import path from "node:path";
import { WorkerRuntime } from "./worker-runtime";
import type { WorkerEvidence, WorkerFeedback, WorkerLifecycleEvent, WorkerTask } from "./worker-types";
let runtime:WorkerRuntime|null=null;
const envBool=(n:string,f:boolean)=>{const r=process.env[n];return r==null?f:["1","true","yes","on"].includes(r.trim().toLowerCase());};
const repoRoot=()=>path.resolve(process.env.MARKETHQ_REPO_ROOT??path.resolve(process.cwd(),".."));
export function getWorkerRuntime(){if(!runtime)runtime=new WorkerRuntime({repoRoot:repoRoot(),enabled:envBool("MARKETHQ_CURSOR_WORKER_ENABLE",false)||envBool("MARKETHQ_HERMES_WORKER_ENABLE",false),maxConcurrency:Math.max(1,Number(process.env.MARKETHQ_WORKER_MAX_CONCURRENCY??1)),defaultTimeoutMs:Math.max(10000,Number(process.env.MARKETHQ_WORKER_TIMEOUT_MS??120000)),defaultMaxAttempts:2});return runtime;}
export const dispatchWorkerTask=(task:WorkerTask)=>getWorkerRuntime().dispatch(task);
export const getWorkerRecord=(id:string)=>getWorkerRuntime().store.latest(id);
export const getWorkerTask=(id:string)=>getWorkerRuntime().store.getTask(id);
export const listWorkerRecords=(limit=50)=>getWorkerRuntime().store.list(limit);
export const listWorkerEvidence=(id:string):WorkerEvidence[]=>getWorkerRuntime().store.listEvidence(id);
export const listWorkerEvents=(id:string,limit=100):WorkerLifecycleEvent[]=>getWorkerRuntime().store.listEvents(id,limit);
export const listWorkerLogs=(id:string,limit=500)=>getWorkerRuntime().store.listLogs(id,limit);
export const getWorkerFeedback=(id:string):WorkerFeedback|null=>getWorkerRuntime().store.latestFeedback(id);
export const getLatestWorkerFeedback=(c:{strategyId?:string;symbol?:string;timeframe?:string})=>getWorkerRuntime().store.latestFeedbackForContext(c);
