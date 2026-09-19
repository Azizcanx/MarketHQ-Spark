import assert from "node:assert/strict";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import test from "node:test";
import { runCursorWorkerPreflight } from "./cursor-worker-preflight";
import type { WorkerTask } from "./worker-types";

const execFileAsync=promisify(execFile);

function task(overrides:Partial<WorkerTask>={}):WorkerTask{
  return{taskId:"preflight-task",runId:"preflight-run",title:"Preflight test",instructions:"Validate preflight safety.",targetPaths:["components/workers"],provider:"cursor",...overrides};
}

async function git(root:string,...args:string[]){await execFileAsync("git",args,{cwd:root});}

async function fixture(){
  const root=await mkdtemp(path.join(os.tmpdir(),"markethq-preflight-"));
  await git(root,"init");
  await git(root,"config","user.email","test@markethq.invalid");
  await git(root,"config","user.name","MarketHQ Test");
  const bin=path.join(root,"fake-cursor-agent");
  await writeFile(bin,"#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo fake-cursor-agent 1.0.0; exit 0; fi\nif [ \"$1\" = \"status\" ]; then echo authenticated; exit 0; fi\nexit 1\n","utf8");
  await chmod(bin,0o755);
  await git(root,"add","fake-cursor-agent");
  await git(root,"commit","-m","fixture");
  return{root,bin};
}

test("Cursor preflight passes with clean git repo, fake CLI and isolated worktree",async()=>{
  const previous=process.env.CURSOR_AGENT_PATH;const f=await fixture();
  try{process.env.CURSOR_AGENT_PATH=f.bin;const result=await runCursorWorkerPreflight({repoRoot:f.root,worktreeRoot:path.join(f.root,".markethq-worktrees"),task:task(),requireAuthentication:true});const failed=result.checks.filter(check=>check.required&&!check.passed).map(check=>`${check.id}: ${check.detail}`);assert.equal(result.ready,true,failed.join("; "));assert.equal(result.status,"READY");assert.equal(result.authStatus,"AUTHENTICATED");assert.equal(result.version,"fake-cursor-agent 1.0.0");assert.ok(result.checks.every(check=>check.passed));}
  finally{if(previous===undefined)delete process.env.CURSOR_AGENT_PATH;else process.env.CURSOR_AGENT_PATH=previous;await rm(f.root,{recursive:true,force:true});}
});

test("Cursor preflight blocks dirty main repo before worker execution",async()=>{
  const previous=process.env.CURSOR_AGENT_PATH;const f=await fixture();
  try{process.env.CURSOR_AGENT_PATH=f.bin;await writeFile(path.join(f.root,"dirty.txt"),"dirty\n","utf8");const result=await runCursorWorkerPreflight({repoRoot:f.root,worktreeRoot:path.join(f.root,".markethq-worktrees"),task:task(),requireAuthentication:true});assert.equal(result.ready,false);assert.equal(result.status,"BLOCKED");assert.equal(result.checks.find(check=>check.id==="main-repo-clean")?.passed,false);}
  finally{if(previous===undefined)delete process.env.CURSOR_AGENT_PATH;else process.env.CURSOR_AGENT_PATH=previous;await rm(f.root,{recursive:true,force:true});}
});

test("Cursor preflight blocks unsafe target traversal",async()=>{
  const previous=process.env.CURSOR_AGENT_PATH;const f=await fixture();
  try{process.env.CURSOR_AGENT_PATH=f.bin;const result=await runCursorWorkerPreflight({repoRoot:f.root,worktreeRoot:path.join(f.root,".markethq-worktrees"),task:task({targetPaths:["../outside"]}),requireAuthentication:true});assert.equal(result.ready,false);assert.equal(result.checks.find(check=>check.id==="target-scope")?.passed,false);}
  finally{if(previous===undefined)delete process.env.CURSOR_AGENT_PATH;else process.env.CURSOR_AGENT_PATH=previous;await rm(f.root,{recursive:true,force:true});}
});
