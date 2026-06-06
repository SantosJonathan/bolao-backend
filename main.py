"""
main.py — API FastAPI para o Bolão Copa do Mundo 2026.

Endpoints públicos:
  GET  /api/dados          → estado completo para o frontend
  POST /api/palpite        → salva palpite (imutável)

Endpoints admin (senha no header X-Admin-Key):
  POST /api/admin/placar       → registra placar real de um jogo
  POST /api/admin/classificacao → registra classificação final

Deploy: Render.com (free tier) — basta apontar para este arquivo.
"""

import os
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from typing import Optional
import logging

from database import (
    init_db, save_palpite, palpite_enviado,
    get_palpite_completo_por_nome, save_placar_real,
    save_classificacao_real, get_placares_reais,
    get_classificacao_real,
)
from scoring import calculate_scores


# ── Config validador de horas ──────────────────────────────
from datetime import datetime
from zoneinfo import ZoneInfo

DATA_LIMITE_PALPITES = datetime(2026, 6, 6, 0, 0, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))   


# ── Config ─────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bolao")

ADMIN_KEY  = os.environ.get("ADMIN_KEY", "#Brasil2026$")
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

app = FastAPI(
    title="Bolão Copa 2026 API",
    description="API para o bolão da Copa do Mundo 2026 — Grupo C Brasil",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    init_db()
    logger.info("✅ Banco inicializado")

# ── Modelos ────────────────────────────────────────────────
class PalpiteInput(BaseModel):
    nome: str
    j1b: int; j1a: int
    j2b: int; j2a: int
    j3b: int; j3a: int
    c1: str; c2: str; c3: str; c4: str

    @field_validator("nome")
    @classmethod
    def nome_valido(cls, v):
        v = v.strip()
        if not v:           raise ValueError("Nome obrigatório")
        if len(v) > 100:    raise ValueError("Nome muito longo")
        return v

    @field_validator("j1b","j1a","j2b","j2a","j3b","j3a")
    @classmethod
    def gols_validos(cls, v):
        if not 0 <= v <= 20: raise ValueError("Gols inválidos (0-20)")
        return v

    @field_validator("c1","c2","c3","c4")
    @classmethod
    def time_valido(cls, v):
        v = v.strip().upper()
        if v not in {"BRASIL","MARROCOS","HAITI","ESCÓCIA"}:
            raise ValueError(f"Time inválido: {v}")
        return v

class PlacarInput(BaseModel):
    jogo: str
    gols_brasil: int
    gols_adversario: int

    @field_validator("jogo")
    @classmethod
    def jogo_valido(cls, v):
        if v not in {"jogo1","jogo2","jogo3"}:
            raise ValueError("Jogo inválido")
        return v

    @field_validator("gols_brasil","gols_adversario")
    @classmethod
    def gols_validos(cls, v):
        if not 0 <= v <= 20: raise ValueError("Gols inválidos")
        return v

class ClassificacaoInput(BaseModel):
    ordem: list[str]

    @field_validator("ordem")
    @classmethod
    def ordem_valida(cls, v):
        validos = {"BRASIL","MARROCOS","HAITI","ESCÓCIA"}
        v = [t.strip().upper() for t in v]
        if len(v) != 4:         raise ValueError("Precisa de exatamente 4 times")
        if len(set(v)) != 4:    raise ValueError("Times não podem se repetir")
        if not set(v) == validos: raise ValueError("Times inválidos")
        return v

# ── Helper auth ────────────────────────────────────────────
def require_admin(x_admin_key: Optional[str] = Header(None)):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Senha de admin incorreta")

# ── Endpoints ──────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "app": "Bolão Copa 2026"}



# @app.get("/api/dados")
# def get_dados():
#     """Retorna todos os dados necessários para o frontend renderizar."""
#     try:
#         placares_reais     = get_placares_reais()
#         classificacao_real = get_classificacao_real()
#         scores             = calculate_scores()

#         JOGOS = [("jogo1","MARROCOS","13/06"),
#                  ("jogo2","HAITI","19/06"),
#                  ("jogo3","ESCÓCIA","24/06")]

#         jogos = []
#         for jkey, adv, data in JOGOS:
#             r = placares_reais.get(jkey, {})
#             jogos.append({
#                 "key": jkey, "adv": adv, "data": data,
#                 "enc": bool(r.get("encerrado")),
#                 "brasil": r.get("brasil"),
#                 "adversario": r.get("adversario"),
#             })

#         ranking = []
#         for i, e in enumerate(scores, 1):
#             det = e["detail"]
#             jd  = []
#             for jkey, _, _ in JOGOS:
#                 d = det.get(jkey, {})
#                 jd.append({
#                     "status":  d.get("status", "pendente"),
#                     "palpite": list(d["palpite"]) if "palpite" in d else [],
#                     "real":    list(d["real"])    if "real"    in d else [],
#                 })
#             cl = det.get("classificacao", {})
#             ranking.append({
#                 "pos":   i,
#                 "nome":  e["nome"],
#                 "total": e["total"],
#                 "jogos": jd,
#                 "cp":    cl.get("palpite", []),
#                 "cr":    cl.get("real", []),
#                 "cs":    {str(k): v for k, v in cl.get("status", {}).items()},
#                 "cpts":  cl.get("pontos", 0),
#             })

#         return {
#             "jogos":   jogos,
#             "ranking": ranking,
#             "cr":      [classificacao_real.get(i, "") for i in range(1, 5)],
#         }
#     except Exception as e:
#         logger.error(f"GET /api/dados: {e}")
#         raise HTTPException(status_code=500, detail="Erro interno")
import time

CACHE_DADOS = {
    "valor": None,
    "expira_em": 0
}

def montar_dados():
    placares_reais     = get_placares_reais()
    classificacao_real = get_classificacao_real()
    scores             = calculate_scores()

    JOGOS = [
        ("jogo1", "MARROCOS", "13/06"),
        ("jogo2", "HAITI", "19/06"),
        ("jogo3", "ESCÓCIA", "24/06")
    ]

    jogos = []
    for jkey, adv, data in JOGOS:
        r = placares_reais.get(jkey, {})
        jogos.append({
            "key": jkey,
            "adv": adv,
            "data": data,
            "enc": bool(r.get("encerrado")),
            "brasil": r.get("brasil"),
            "adversario": r.get("adversario"),
        })

    ranking = []
    for i, e in enumerate(scores, 1):
        det = e["detail"]
        jd = []

        for jkey, _, _ in JOGOS:
            d = det.get(jkey, {})
            jd.append({
                "status": d.get("status", "pendente"),
                "palpite": list(d["palpite"]) if "palpite" in d else [],
                "real": list(d["real"]) if "real" in d else [],
            })

        cl = det.get("classificacao", {})

        ranking.append({
            "pos": i,
            "nome": e["nome"],
            "total": e["total"],
            "jogos": jd,
            "cp": cl.get("palpite", []),
            "cr": cl.get("real", []),
            "cs": {str(k): v for k, v in cl.get("status", {}).items()},
            "cpts": cl.get("pontos", 0),
        })

    return {
        "jogos": jogos,
        "ranking": ranking,
        "cr": [classificacao_real.get(i, "") for i in range(1, 5)],
    }


@app.get("/api/dados")
def get_dados():
    try:
        agora = time.time()

        if CACHE_DADOS["valor"] is not None and agora < CACHE_DADOS["expira_em"]:
            return CACHE_DADOS["valor"]

        inicio = time.time()

        resultado = montar_dados()

        CACHE_DADOS["valor"] = resultado
        CACHE_DADOS["expira_em"] = agora + 60

        logger.info(f"GET /api/dados gerado em {time.time() - inicio:.2f}s")

        return resultado

    except Exception as e:
        logger.error(f"GET /api/dados: {e}")
        raise HTTPException(status_code=500, detail="Erro interno")

@app.post("/api/palpite")
def post_palpite(body: PalpiteInput):
    """Registra palpite. Imutável — uma vez enviado não pode ser alterado."""
    try:
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
        if agora >= DATA_LIMITE_PALPITES:
            logger.warning(f"⛔ Palpite rejeitado (fora do prazo). Nome: {body.nome}")
            raise HTTPException(status_code=403, detail="Prazo para envio de palpites encerrado.")

        nome = body.nome

        if palpite_enviado(nome):
            raise HTTPException(status_code=409,
                                detail=f"Palpite de '{nome}' já registrado e não pode ser alterado.")

        classif_vals = [body.c1, body.c2, body.c3, body.c4]
        if len(set(classif_vals)) != 4:
            raise HTTPException(status_code=422, detail="Times da classificação não podem se repetir.")

        palpites = {
            "jogo1": (body.j1b, body.j1a),
            "jogo2": (body.j2b, body.j2a),
            "jogo3": (body.j3b, body.j3a),
        }
        ok = save_palpite(nome, palpites, tuple(classif_vals))
        if not ok:
            raise HTTPException(status_code=409,
                                detail=f"Palpite de '{nome}' já registrado.")

        logger.info(f"✅ Palpite salvo: {nome}")
        return {"ok": True, "msg": f"🎉 Palpite de {nome} registrado! Boa sorte!"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"POST /api/palpite: {e}")
        raise HTTPException(status_code=500, detail="Erro ao salvar palpite")


@app.post("/api/admin/placar")
def post_placar(body: PlacarInput, x_admin_key: Optional[str] = Header(None)):
    require_admin(x_admin_key)
    try:
        save_placar_real(body.jogo, body.gols_brasil, body.gols_adversario)
        logger.info(f"✅ Placar real: {body.jogo} {body.gols_brasil}×{body.gols_adversario}")
        return {"ok": True, "msg": "✅ Placar salvo!"}
    except Exception as e:
        logger.error(f"POST /api/admin/placar: {e}")
        raise HTTPException(status_code=500, detail="Erro ao salvar placar")


@app.post("/api/admin/classificacao")
def post_classificacao(body: ClassificacaoInput, x_admin_key: Optional[str] = Header(None)):
    require_admin(x_admin_key)
    try:
        save_classificacao_real(body.ordem)
        logger.info(f"✅ Classificação: {body.ordem}")
        return {"ok": True, "msg": "✅ Classificação salva!"}
    except Exception as e:
        logger.error(f"POST /api/admin/classificacao: {e}")
        raise HTTPException(status_code=500, detail="Erro ao salvar classificação")


@app.get("/api/health")
def health():
    return {"status": "healthy", "db": "postgres" if USE_PG else "sqlite"}


# ── Dev server ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
