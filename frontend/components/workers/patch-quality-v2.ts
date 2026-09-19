import type { WorkerEvidence, WorkerFeedback, WorkerRecord, WorkerTask } from "./worker-types";

export type WorkerPatchQuality = {
  status: "ACCEPTED" | "REVIEW_REQUIRED" | "REJECTED" | "NO_PATCH" | "FAILED" | "UNKNOWN";
  score: number; grade: "A" | "B" | "C" | "D" | "F";
  changedFileCount: number; targetFileCount: number; scopeCompliant: boolean; hasPatch: boolean;
  validationAttempted: boolean; validationPassed: boolean; validationFailures: number; unsafeEvidence: boolean;
  evidenceQuality: "HIGH" | "MEDIUM" | "LOW" | "NONE"; recommendation: "ACCEPT" | "REVIEW" | "FEED_BACK" | "NO_PATCH"; reason: string;
};

const norm=(v:string)=>v.replace(/\\/g,"/").replace(/^\.\//,"").replace(/\/$/,"");
const inScope=(file:string,target:string)=>{const f=norm(file),t=norm(target);return f===t||f.startsWith(`${t}/`);};

export function buildWorkerPatchQuality(record:WorkerRecord|null,task:WorkerTask|null,evidence:WorkerEvidence[],feedback?:WorkerFeedback|null):WorkerPatchQuality{
 const changed=[...new Set(evidence.flatMap(e=>e.changedFiles))]; const targets=task?.targetPaths??[];
 const validationAttempted=evidence.some(e=>Boolean(e.validation?.attempted));
 const validationPassed=evidence.some(e=>Boolean(e.validation?.attempted&&e.validation.passed));
 const validationFailures=evidence.filter(e=>Boolean(e.validation?.attempted&&!e.validation.passed)).length;
 const hasPatch=evidence.some(e=>Boolean(e.diff))||changed.length>0;
 const unsafe=evidence.some(e=>!e.safety.researchOnly||e.safety.mainRepoMutation||e.safety.automaticPr||e.safety.automaticMerge||!e.safety.isolatedWorktree);
 const scopeCompliant=targets.length>0&&changed.every(file=>targets.some(target=>inScope(file,target)));
 const evidenceQuality=feedback?.evidenceQuality??(validationPassed&&hasPatch?"HIGH":validationPassed||hasPatch?"MEDIUM":evidence.length?"LOW":"NONE");
 const raw=record?.status; const status:WorkerPatchQuality["status"]=raw==="ACCEPTED"?"ACCEPTED":raw==="REVIEW_REQUIRED"?"REVIEW_REQUIRED":raw==="PATCH_REJECTED"?"REJECTED":raw==="NO_PATCH"?"NO_PATCH":raw==="FAILED_FINAL"?"FAILED":"UNKNOWN";
 let score=0; if(hasPatch)score+=30;if(validationAttempted)score+=20;if(validationPassed)score+=30;if(scopeCompliant)score+=10;if(evidenceQuality==="HIGH")score+=10;else if(evidenceQuality==="MEDIUM")score+=5;if(validationFailures)score-=Math.min(20,validationFailures*10);if(!scopeCompliant)score-=30;if(unsafe)score=0;score=Math.max(0,Math.min(100,score));
 const grade=score>=90?"A":score>=80?"B":score>=65?"C":score>=50?"D":"F";
 const recommendation=feedback?.recommendation??(unsafe||!scopeCompliant||status==="REVIEW_REQUIRED"?"REVIEW":(status==="ACCEPTED"||status==="UNKNOWN")&&validationPassed?"ACCEPT":status==="NO_PATCH"?"NO_PATCH":"FEED_BACK");
 const reason=unsafe?"Safety evidence invalidates acceptance.":!scopeCompliant?"Changed files are outside the declared target scope.":!hasPatch?"No patch was produced.":validationPassed?"Patch and validation evidence are present.":validationAttempted?"Patch exists but validation did not pass.":"Patch exists without validation evidence.";
 return {status,score,grade,changedFileCount:changed.length,targetFileCount:targets.length,scopeCompliant,hasPatch,validationAttempted,validationPassed,validationFailures,unsafeEvidence:unsafe,evidenceQuality,recommendation,reason};
}
