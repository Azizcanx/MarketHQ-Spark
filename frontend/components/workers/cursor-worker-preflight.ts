import { execFile } from "node:child_process";
import { promisify } from "node:util";
import os from "node:os";
import path from "node:path";
import type { WorkerTask } from "./worker-types";
import { currentWorkerRuntimeGate } from "./runtime-gate";

const execFileAsync=promisify(execFile);
export type CursorPreflightStatus="READY"|"BLOCKED";
export type CursorPreflightCheck={id:string;passed:boolean;required:boolean;detail:string};
export type CursorWorkerPreflightResult={status:CursorPreflightStatus;ready:boolean;checks:CursorPreflightCheck[];executable?:string;version?:string;authStatus?:"AUTHENTICATED"|"NOT_AUTHENTICATED"|"UNKNOWN";checkedAt:string};
export class CursorWorkerPreflightBlockedError extends Error{readonly preflight:CursorWorkerPreflightResult;constructor(p:CursorWorkerPreflightResult){super(`Cursor worker preflight blocked: ${p.checks.filter(x=>x.required&&!x.passed).map(x=>x.id).join(", ")}`);this.preflight=p;}}

async function runCli(executable:string,args:string[]){
  const isWindowsCmd=process.platform==="win32"&&/\.(cmd|bat)$/i.test(executable);
  if(isWindowsCmd)return execFileAsync(process.env.ComSpec||"cmd.exe",["/d","/s","/c","call",executable,...args],{windowsHide:true,timeout:10000});
  return execFileAsync(executable,args,{windowsHide:true,timeout:10000});
}

async function gitStatus(repoRoot:string){
  try{const r=await execFileAsync("git",["status","--porcelain"],{cwd:repoRoot,windowsHide:true,timeout:10000,maxBuffer:2*1024*1024});return{ok:true,dirty:String(r.stdout).trim().length>0};}catch{return{ok:false,dirty:true};}
}
function safeRelative(value:string){if(!value||path.isAbsolute(value))return false;const normalized=path.normalize(value);return normalized!==".."&&!normalized.startsWith(`..${path.sep}`);}
function candidates(){
  const values=[process.env.CURSOR_AGENT_PATH,"agent","agent.exe"];
  const home=os.homedir();
  if(home){
    values.push(path.join(home,".local","bin","agent"));
    values.push(path.join(home,".local","bin","agent.exe"));
    values.push(path.join(home,".cursor","bin","agent"));
    values.push(path.join(home,".cursor","bin","agent.exe"));
  }
  if(process.platform==="win32"){
    const local=process.env.LOCALAPPDATA;
    if(local){
      values.push(path.join(local,"cursor-agent","agent.cmd"));
      values.push(path.join(local,"cursor-agent","agent.exe"));
      values.push(path.join(local,"Programs","cursor-agent","agent.cmd"));
      values.push(path.join(local,"Programs","cursor-agent","agent.exe"));
    }
  }
  return[...new Set(values.filter(Boolean) as string[])];
}
async function cli(){for(const c of candidates()){try{const r=await runCli(c,["--version"]);return{executable:c,version:String(r.stdout).trim()};}catch{}}return null;}

export async function runCursorWorkerPreflight(input:{repoRoot:string;worktreeRoot:string;task:WorkerTask;requireAuthentication?:boolean;allowDirtyMainRepo?:boolean}):Promise<CursorWorkerPreflightResult>{
  const checks:CursorPreflightCheck[]=[];const repoRoot=path.resolve(input.repoRoot);const worktreeRoot=path.resolve(input.worktreeRoot);const gate=currentWorkerRuntimeGate();const relativeTargets=input.task.targetPaths.length>0&&input.task.targetPaths.every(safeRelative);const gitState=await gitStatus(repoRoot);const allowDirty=input.allowDirtyMainRepo===true;
  checks.push({id:"runtime-safety-gate",passed:gate.researchOnly&&!gate.executionEnabled&&!gate.databaseWriteEnabled&&!gate.brokerExecutionEnabled,required:true,detail:"Research-only runtime gate"});
  checks.push({id:"repo-root",passed:!!input.repoRoot&&repoRoot!==path.parse(repoRoot).root,required:true,detail:repoRoot});
  checks.push({id:"main-repo-git",passed:gitState.ok,required:true,detail:gitState.ok?"Git repository is reachable":"Git repository could not be verified"});
  checks.push({id:"main-repo-clean",passed:gitState.ok&&(allowDirty||!gitState.dirty),required:true,detail:gitState.dirty?(allowDirty?"Main repository is dirty; explicit override enabled":"Main repository has uncommitted changes"):"Main repository is clean"});
  checks.push({id:"target-scope",passed:relativeTargets,required:true,detail:"Explicit relative target paths without traversal"});
  checks.push({id:"mutation-authority",passed:gate.mainRepoMutation===false&&input.task.metadata?.mutationAuthorized!==true,required:true,detail:"Main repository mutation disabled"});
  checks.push({id:"pr-merge-authority",passed:gate.automaticPr===false&&gate.automaticMerge===false&&input.task.metadata?.automaticPr!==true&&input.task.metadata?.automaticMerge!==true,required:true,detail:"PR/merge disabled"});
  const c=await cli();checks.push({id:"cursor-cli",passed:!!c,required:true,detail:c?`${c.executable} ${c.version}`:"Cursor Agent CLI not found"});
  let auth:"AUTHENTICATED"|"NOT_AUTHENTICATED"|"UNKNOWN"="UNKNOWN";if(c){try{await runCli(c.executable,["status"]);auth="AUTHENTICATED";}catch{auth="NOT_AUTHENTICATED";}}
  const requiredAuth=input.requireAuthentication!==false;checks.push({id:"cursor-auth",passed:!requiredAuth||auth==="AUTHENTICATED",required:requiredAuth,detail:auth});
  checks.push({id:"isolated-worktree",passed:worktreeRoot!==repoRoot,required:true,detail:worktreeRoot});
  checks.push({id:"main-repo-mutation",passed:false===gate.mainRepoMutation,required:true,detail:"false"});checks.push({id:"automatic-pr",passed:false===gate.automaticPr,required:true,detail:"false"});checks.push({id:"automatic-merge",passed:false===gate.automaticMerge,required:true,detail:"false"});
  const ready=checks.every(x=>!x.required||x.passed);return{status:ready?"READY":"BLOCKED",ready,checks,executable:c?.executable,version:c?.version,authStatus:auth,checkedAt:new Date().toISOString()};
}
