#!/usr/bin/env python3
import argparse, datetime as dt, json, os, re, shutil, sys
from pathlib import Path
from urllib import error, request

CODE_EXTENSIONS={".py",".js",".ts",".tsx",".jsx",".java",".cpp",".c",".cs",".go",".rs",".php",".rb",".swift",".kt",".kts",".html",".css",".scss",".json",".xml",".yml",".yaml",".sql",".sh",".ps1"}
DEFAULT_MODEL=os.environ.get("OLLAMA_MODEL","qwen2.5-coder:1.5b")
DEFAULT_BASE_URL=os.environ.get("OLLAMA_BASE_URL","http://127.0.0.1:11434")

class AgentError(Exception): pass

class Agent:
    def __init__(self, workspace: str, model: str, base_url: str, timeout: int = 180):
        self.root=Path(workspace).expanduser().resolve()
        self.model=model
        self.base_url=base_url.rstrip("/")
        self.timeout=timeout
        self.ready=False

    def info(self,msg:str)->None: print(f"[info] {msg}")
    def err(self,msg:str)->None: print(f"[error] {msg}")

    def api(self, method:str, path:str, payload:dict|None=None)->dict:
        req=request.Request(f"{self.base_url}{path}",data=None if payload is None else json.dumps(payload).encode("utf-8"),headers={"Content-Type":"application/json"},method=method)
        try:
            with request.urlopen(req, timeout=self.timeout) as r:
                raw=r.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except error.HTTPError as e:
            raise AgentError(f"Ollama request failed: HTTP {e.code}. {e.read().decode('utf-8', errors='replace')}") from e
        except error.URLError as e:
            raise AgentError("Could not reach Ollama. Make sure Ollama is installed and the local server is running.") from e
        except TimeoutError as e:
            raise AgentError("Timed out while waiting for Ollama.") from e

    def ensure_model(self)->None:
        if self.ready: return
        names={m.get("name","") for m in self.api("GET","/api/tags").get("models",[])}
        if self.model not in names:
            raise AgentError(f"Model '{self.model}' is not available in Ollama. Run: ollama pull {self.model}")
        self.ready=True

    def chat_json(self, system:str, user:str)->dict:
        self.ensure_model()
        data=self.api("POST","/api/chat",{"model":self.model,"stream":False,"format":"json","messages":[{"role":"system","content":system},{"role":"user","content":user}],"options":{"temperature":0.2}})
        content=data.get("message",{}).get("content","").strip()
        if not content: raise AgentError("The model returned an empty response.")
        try: return json.loads(content)
        except json.JSONDecodeError as e: raise AgentError(f"The model returned invalid JSON: {content[:300]}") from e

    def tools(self)->dict:
        return {
            "create":{"keywords":("create","make","generate","build","write"),"needs_model":True,"run":self.create},
            "read":{"keywords":("read","show","print file","display"),"needs_model":False,"run":self.read},
            "modify":{"keywords":("modify","update","change","refactor","edit","rewrite","fix"),"needs_model":True,"run":self.modify},
        }

    def code_files(self)->list[str]:
        files=[]
        for p in self.root.rglob("*"):
            if p.is_file() and p.suffix.lower() in CODE_EXTENSIONS: files.append(p.relative_to(self.root).as_posix())
            if len(files)>=200: break
        return sorted(files)

    def safe_rel(self, value:str)->str:
        value=value.strip().replace("\\","/").lstrip("/")
        parts=[p for p in value.split("/") if p not in {"","."}]
        if not parts or ":" in value or any(p==".." for p in parts): raise AgentError("Paths outside the workspace are not allowed.")
        return "/".join(parts)

    def path(self, relative:str)->Path:
        p=(self.root/self.safe_rel(relative)).resolve()
        try: p.relative_to(self.root)
        except ValueError as e: raise AgentError("The requested path is outside the workspace.") from e
        return p

    def file_ref(self, text:str)->str|None:
        for pattern in (r"`([^`]+\.\w+)`",r'"([^"]+\.\w+)"',r"'([^']+\.\w+)'",r"\b([A-Za-z0-9_\-./\\]+\.\w+)\b"):
            match=re.search(pattern,text)
            if match: return match.group(1)
        return None

    def pick_file(self, text:str)->tuple[Path,str]:
        ref=self.file_ref(text)
        if ref:
            ref=ref.replace("\\","/")
            direct=self.path(ref)
            if direct.exists() and direct.is_file(): return direct,direct.relative_to(self.root).as_posix()
            matches=[p for p in self.root.rglob(Path(ref).name) if p.is_file()]
            if len(matches)==1: return matches[0],matches[0].relative_to(self.root).as_posix()
            if len(matches)>1: raise AgentError(f"Multiple files match '{ref}': {', '.join(p.relative_to(self.root).as_posix() for p in matches[:5])}")
            raise AgentError(f"File '{ref}' does not exist inside the workspace.")
        files=self.code_files()
        if not files: raise AgentError("No code files were found in the workspace.")
        if len(files)==1: return self.path(files[0]),files[0]
        raise AgentError(f"Your request does not name a file clearly enough. Available files include: {', '.join(files[:8])}")

    def unique_path(self, relative:str)->tuple[Path,str]:
        p=self.path(relative)
        if not p.exists(): return p,self.safe_rel(relative)
        for i in range(1,1000):
            alt=p.with_name(f"{p.stem}_{i}{p.suffix}")
            if not alt.exists(): return alt,alt.relative_to(self.root).as_posix()
        raise AgentError("Could not find a free file name.")

    def backup(self, path:Path)->Path:
        copy=path.with_name(f"{path.name}.{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.bak")
        shutil.copy2(path,copy)
        return copy

    def classify(self, text:str)->str:
        lower=text.lower()
        for name,tool in self.tools().items():
            if any(k in lower for k in tool["keywords"]): return name
        result=self.chat_json("Classify the coding request. Return JSON with one key named intent. Valid values: create, read, modify, unclear.",f"User request: {text}\nCode files in workspace: {json.dumps(self.code_files()[:50])}")
        return result.get("intent","").strip().lower()

    def create(self, text:str)->None:
        result=self.chat_json(
            "You create a single code file inside a workspace. Return strict JSON with keys: relative_path, content, summary. The path must be relative, stay inside the workspace, and use a suitable extension. The content must be the full file with no markdown fences.",
            f"User request: {text}\nExisting files in workspace: {json.dumps(self.code_files()[:100])}\nChoose one good file path and generate the full file content.",
        )
        rel,content,summary=str(result.get("relative_path","")).strip(),str(result.get("content","")),str(result.get("summary","")).strip()
        if not rel or not content.strip(): raise AgentError("The model returned an invalid or empty create response.")
        path,final_rel=self.unique_path(rel); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding="utf-8")
        self.info(f"Created file: {final_rel}")
        if summary: print(summary)

    def read(self, text:str)->None:
        path,rel=self.pick_file(text)
        self.info(f"Read file: {rel}")
        print(path.read_text(encoding="utf-8"))

    def modify(self, text:str)->None:
        path,rel=self.pick_file(text); code=path.read_text(encoding="utf-8"); backup=self.backup(path)
        result=self.chat_json(
            "You modify an existing code file. Return strict JSON with keys: updated_content, summary. The updated_content value must contain the complete new file content with no markdown fences.",
            f"User request: {text}\nTarget file: {rel}\n\nExisting code:\n{code}\n\nApply the requested change and return the full updated file.",
        )
        updated,summary=str(result.get("updated_content","")),str(result.get("summary","")).strip()
        if not updated.strip(): raise AgentError("The model returned an invalid or empty modify response.")
        path.write_text(updated, encoding="utf-8")
        self.info(f"Modified file: {rel}"); self.info(f"Backup created: {backup.name}")
        if summary: print(summary)

    def run(self, text:str)->None:
        tool=self.classify(text)
        if tool in self.tools(): self.tools()[tool]["run"](text); return
        raise AgentError("The request is unclear. Try starting with Create, Read, or Modify and include a file name when needed.")

def ask_workspace(value:str|None)->str:
    while True:
        value=value or input("Workspace folder: ").strip()
        if not value: print("[error] Please enter a workspace folder."); value=None; continue
        if Path(value).expanduser().is_dir(): return value
        print("[error] That folder does not exist."); value=None

def ask_request(value:str|None)->str:
    text=value or input("Request: ").strip()
    if not text: raise AgentError("The request is empty.")
    return text

def main()->int:
    parser=argparse.ArgumentParser(description="Simple terminal coding agent using Ollama.")
    parser.add_argument("--workspace"); parser.add_argument("--request"); parser.add_argument("--model", default=DEFAULT_MODEL); parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args=parser.parse_args(); agent=Agent(ask_workspace(args.workspace), args.model, args.base_url)
    if args.request:
        try: agent.run(args.request); return 0
        except (AgentError, UnicodeDecodeError) as e: agent.err("The selected file could not be read as UTF-8 text." if isinstance(e, UnicodeDecodeError) else str(e)); return 1
    agent.info("Type requests like 'Create a Python file that prints Hello World.'"); agent.info("Type 'exit' or 'quit' to stop.")
    while True:
        try:
            text=ask_request(None)
            if text.lower() in {"exit","quit"}: agent.info("Goodbye."); return 0
            agent.run(text)
        except (AgentError, UnicodeDecodeError) as e:
            agent.err("The selected file could not be read as UTF-8 text." if isinstance(e, UnicodeDecodeError) else str(e))
        except KeyboardInterrupt:
            print(); agent.info("Stopped by user."); return 0

if __name__=="__main__": sys.exit(main())
