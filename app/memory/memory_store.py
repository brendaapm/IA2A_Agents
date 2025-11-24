# SQLite/JSON p/ conclusões
import json
from pathlib import Path
from typing import List


class Memory:
    def __init__(self, path: str = "mem.jsonl"):
        self.path = Path(path)
        if not self.path.exists():
            self.path.write_text("")

    def add(self, text: str):
        record = {"text": text}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def get_all(self) -> List[str]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        out = []
        for ln in lines:
            try:
                out.append(json.loads(ln).get("text", ""))
            except Exception:
                continue
        return [x for x in out if x]

    def get_all_as_markdown(self) -> str:
        items = self.get_all()
        if not items:
            return "_Sem conclusões salvas ainda._"
        return "\n".join([f"- {t}" for t in items])
    
    def clear(self):
        """Apaga toda a memória desta sessão (trunca o arquivo)."""
        self.path.write_text("")