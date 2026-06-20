# 🇧🇷 Bolão Copa do Mundo 2026 — Grupo C

Frontend HTML/CSS/JS puro + Backend FastAPI + Supabase PostgreSQL.

## Arquitetura

```
GitHub Pages ou Netlify (frontend)
        ↓ fetch() POST/GET
FastAPI no Render.com (backend)
        ↓
Supabase PostgreSQL (banco de dados persistente)
```

---

## 🗄️ 1. Supabase (banco de dados)

1. Crie conta em [supabase.com](https://supabase.com)
2. Crie projeto `bolao-copa`
3. Vá em **Settings → Database → Connection string → URI**
4. Copie a connection string no formato:
   ```
   postgresql://postgres:SENHA@db.SEU-ID.supabase.co:5432/postgres
   ```

---

## 🚀 2. Deploy do Backend (Render.com)

1. Crie conta em [render.com](https://render.com)
2. **New → Web Service**
3. Conecte o repositório GitHub (suba a pasta `backend/`)
4. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Em **Environment Variables**, adicione:
   ```
   DATABASE_URL = postgresql://postgres:SENHA@db.SEU-ID.supabase.co:5432/postgres
   ADMIN_KEY    = sua_senha_admin_aqui
   ALLOWED_ORIGINS = https://seu-frontend.netlify.app
   ```
6. Clique **Create Web Service**
7. Aguarde o deploy (~2 min). Copie a URL: `https://bolao-api.onrender.com`

---

## 🌐 3. Deploy do Frontend (Netlify — gratuito)

### Opção A — Netlify Drop (mais simples)
1. Acesse [app.netlify.com/drop](https://app.netlify.com/drop)
2. Arraste a pasta `frontend/` para a área indicada
3. Pronto! Copie a URL gerada (ex: `https://bolao-copa2026.netlify.app`)

### Opção B — GitHub + Netlify (automático)
1. Suba a pasta `frontend/` no GitHub
2. Conecte ao Netlify → deploy automático a cada `git push`

### Configure a URL da API no frontend
Edite `frontend/index.html`, linha com `window.BOLAO_API_URL`:
```javascript
const API_URL = window.BOLAO_API_URL || 'https://bolao-api.onrender.com';
```
Ou crie um arquivo `frontend/config.js`:
```javascript
window.BOLAO_API_URL = 'https://bolao-api.onrender.com';
```
E inclua no `index.html` antes do `</head>`:
```html
<script src="config.js"></script>
```

---

## 🔒 Admin

- Acesse a aba **ADMIN** no frontend
- Digite a senha configurada em `ADMIN_KEY` no Render
- Registre placares reais após cada jogo
- Registre a classificação final do grupo

---

## 💻 Rodando localmente

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
# API em: http://localhost:8000

# Frontend
# Abra frontend/index.html diretamente no navegador
# OU use um servidor local:
cd frontend && python -m http.server 3000
# Acesse: http://localhost:3000
```

---

## 📊 Pontuação

| Acerto | Pontos |
|--------|--------|
| Placar exato de um jogo | **50 pts** |
| Acertar 1 posição individual na classificação | **30 pts** |
| Gabaritar toda a classificação (bônus) | **+100 pts** |

Em caso de empate: 1º mais placares exatos, 2º mais acertos de ordem, 3º sorteio.

---

## 🗓️ Jogos do Brasil — Grupo C

| Jogo | Data | Adversário |
|------|------|-----------|
| Jogo 1 | 13/06 | Marrocos |
| Jogo 2 | 19/06 | Haiti |
| Jogo 3 | 24/06 | Escócia |

---

## 📁 Estrutura

```
bolao_copa2026/
├── backend/
│   ├── main.py          ← API FastAPI
│   ├── database.py      ← SQLite local / PostgreSQL produção
│   ├── scoring.py       ← Lógica de pontuação
│   └── requirements.txt
└── frontend/
    └── index.html       ← App completo (HTML + CSS + JS)
```
