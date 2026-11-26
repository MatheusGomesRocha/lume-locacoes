"""Gera a pasta versao-pages a partir de versao-real/frontend.

A versão de demonstração é o MESMO front, só que travado no modo "local" (dados no navegador).
Rode de novo sempre que mudar algo no front real:  python scripts/exportar_pages.py
"""
import json
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGEM = RAIZ / "versao-real" / "frontend"
DESTINO = RAIZ / "versao-pages"
IGNORAR = shutil.ignore_patterns("node_modules", "dist", ".env.local", "*.local", "*.tsbuildinfo")

# versao-pages é um repositório git à parte: limpa o conteúdo, mas preserva .git, .github (CI/CD) e o README
MANTER = {".git", ".github", "README.md"}
DESTINO.mkdir(exist_ok=True)
README_DA_DEMO = (DESTINO / "README.md").read_bytes() if (DESTINO / "README.md").exists() else None
for item in DESTINO.iterdir():
    if item.name in MANTER:
        continue
    shutil.rmtree(item) if item.is_dir() else item.unlink()
shutil.copytree(ORIGEM, DESTINO, ignore=IGNORAR, dirs_exist_ok=True)
if README_DA_DEMO is not None:  # o README do front real não pode sobrescrever o da demonstração
    (DESTINO / "README.md").write_bytes(README_DA_DEMO)

# modo local fixo (o build não depende de variável para escolher o driver)
(DESTINO / ".env.production").write_text(
    "# Demonstração: dados ficam no navegador (localStorage).\n"
    "VITE_DRIVER=local\n"
    "# URL da API Python hospedada (Render). Pode ser sobrescrita no build.\n"
    "VITE_IA_API_URL=\n",
    encoding="utf-8",
)
(DESTINO / ".env.example").write_text("VITE_DRIVER=local\nVITE_IA_API_URL=http://127.0.0.1:8001\n", encoding="utf-8")
(DESTINO / ".env.development").write_text("VITE_DRIVER=local\nVITE_IA_API_URL=http://127.0.0.1:8001\n", encoding="utf-8")

pacote = json.loads((DESTINO / "package.json").read_text(encoding="utf-8"))
pacote["name"] = "lume-demo"
(DESTINO / "package.json").write_text(json.dumps(pacote, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print("versao-pages gerada em", DESTINO)
