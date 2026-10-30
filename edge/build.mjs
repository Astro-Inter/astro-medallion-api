import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
const local=process.platform==="win32"?".venv/Scripts/python.exe":".venv/bin/python";
const python=process.env.PYTHON||(existsSync(local)?local:"python");
const result=spawnSync(python,["edge/build_contract.py"],{stdio:"inherit",shell:false});
if(result.error) { console.error(result.error.message); process.exit(1); }
process.exit(result.status??1);
