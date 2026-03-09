# 🛡️ SuperGuard — Sistema de Segurança Inteligente para Supermercados

> Sistema de visão computacional para detecção em tempo real de furtos/roubos em supermercados, com alertas imediatos via Telegram e painel web de monitoramento.

---

## 📋 Índice

1. [Arquitetura](#arquitetura)
2. [Estrutura de Pastas](#estrutura-de-pastas)
3. [Pré-requisitos](#pré-requisitos)
4. [Instalação e Execução Local](#instalação-e-execução-local)
5. [Deploy em Produção (VPS)](#deploy-em-produção-vps)
6. [Configuração do Bot Telegram](#configuração-do-bot-telegram)
7. [Comandos do Bot](#comandos-do-bot)
8. [API REST](#api-rest)
9. [Treinamento/Fine-tuning do Modelo](#treinamentofine-tuning-do-modelo)
10. [Suposições e Decisões de Design](#suposições-e-decisões-de-design)
11. [⚙️ Abrindo o Projeto no PyCharm](#️-abrindo-o-projeto-no-pycharm)

---

## 🏗️ Arquitetura

```
┌──────────────────────────────────────────────────────────────────┐
│                         Docker Compose                           │
│                                                                  │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐  │
│  │   worker_cv     │    │      api        │    │  postgres   │  │
│  │                 │    │                 │    │             │  │
│  │  YOLO + OpenCV  │───▶│  FastAPI        │───▶│ PostgreSQL  │  │
│  │  (4+ câmeras)   │    │  Telegram Bot   │    │  SQLAlchemy │  │
│  │  supervision    │    │  Painel Web     │    │  Alembic    │  │
│  └─────────────────┘    └────────┬────────┘    └─────────────┘  │
│          │                       │                               │
│          └───── alerts/ ─────────┘                               │
│               (fotos JPG)                                        │
└──────────────────────────────────────────────────────────────────┘
          │                         │
          ▼                         ▼
   📹 Câmeras RTSP          📱 Telegram Bot
   (múltiplas URLs)          + Painel Web :8000
```

### Fluxo de Detecção

```
Câmera RTSP → CameraWorker thread → YOLO detecta pessoas/objetos
    → Score de suspeita calculado
    → Debounce 30s por câmera
    → Frame salvo como JPEG (não grava vídeo - LGPD compliant)
    → POST /api/alertas/interno
    → Salvo no PostgreSQL
    → Enviado a todos usuários autorizados via Telegram
```

---

## 📁 Estrutura de Pastas

```
superguard/
├── docker-compose.yml          # Orquestração dos serviços
├── Dockerfile.api              # Imagem para API + Bot Telegram
├── Dockerfile.cv               # Imagem para Worker de Visão Computacional
├── requirements.txt            # Dependências Python 3.12
├── .env.example                # Modelo de variáveis de ambiente
├── alembic.ini                 # Configuração do Alembic
├── pytest.ini                  # Configuração de testes
│
├── app/
│   ├── __init__.py
│   ├── core/
│   │   ├── config.py           # Configurações via Pydantic Settings
│   │   └── auth.py             # JWT + bcrypt
│   ├── models/
│   │   └── database.py         # SQLAlchemy 2.0: User, Camera, Alert
│   ├── cv/
│   │   ├── detector.py         # DetectorFurto com YOLO
│   │   ├── tracker.py          # RastreadorFurto com supervision/ByteTrack
│   │   └── main.py             # Worker principal (multi-thread por câmera)
│   ├── bot/
│   │   └── telegram_bot.py     # Bot Telegram completo
│   └── api/
│       ├── main.py             # FastAPI app + lifecycle
│       ├── routes/
│       │   ├── auth.py         # JWT login
│       │   ├── alerts.py       # CRUD alertas
│       │   ├── cameras.py      # CRUD câmeras
│       │   ├── users.py        # CRUD usuários
│       │   └── web.py          # Painel HTML
│       └── templates/
│           ├── login.html      # Página de login
│           ├── dashboard.html  # Dashboard principal
│           ├── alertas.html    # Histórico de alertas
│           └── usuarios.html   # Gerenciar usuários
│
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 001_initial.py      # Migração inicial
│
├── tests/
│   ├── test_detector.py        # Testes unitários da detecção
│   ├── test_tracker.py         # Testes do rastreador
│   └── test_telegram_mock.py   # Testes de integração do bot
│
└── alerts/                     # Fotos de alertas (volume Docker)
```

---

## 📦 Pré-requisitos

- **Docker** ≥ 24.0 e **Docker Compose** ≥ 2.20
- **Python 3.12** (para desenvolvimento local)
- Token do **Telegram Bot** (obtido via [@BotFather](https://t.me/botfather))
- Câmeras com URL **RTSP** ou HTTP acessíveis na rede

---

## 🚀 Instalação e Execução Local

### 1. Clone e configure o ambiente

```bash
git clone <url-do-repo>
cd superguard

# Copie e edite as variáveis de ambiente
cp .env.example .env
nano .env
```

### 2. Configure o `.env`

Edite os campos obrigatórios:

```env
# Token do seu bot Telegram
TELEGRAM_BOT_TOKEN=1234567890:ABCdef...

# Seu chat ID do Telegram (obtenha com @userinfobot)
TELEGRAM_ADMIN_CHAT_ID=987654321

# URLs das câmeras RTSP (separadas por vírgula)
CAMERA_URLS=rtsp://admin:senha@192.168.1.100:554/stream,rtsp://admin:senha@192.168.1.101:554/stream
CAMERA_NAMES=Entrada Principal,Caixa 01

# Senha segura para o banco
POSTGRES_PASSWORD=minha_senha_segura

# Chave JWT (gere com: python -c "import secrets; print(secrets.token_hex(32))")
SECRET_KEY=sua_chave_secreta_aqui
```

### 3. Suba os serviços

```bash
# Constrói as imagens e inicia todos os serviços
docker compose up --build

# Ou em background
docker compose up --build -d
```

### 4. Primeiro acesso

```bash
# Acompanhe os logs
docker compose logs -f api
docker compose logs -f worker_cv

# O painel web estará disponível em:
# http://localhost:8000
```

### 5. Crie o primeiro admin

Via Telegram — envie `/start` ao seu bot, depois `/registrar`.
O bot notificará você (usando `TELEGRAM_ADMIN_CHAT_ID`) para aprovar via `/adduser`.

Ou diretamente via API:

```bash
# Cria usuário admin com senha para o painel web
curl -X POST http://localhost:8000/api/usuarios \
  -H "Content-Type: application/json" \
  -d '{"chat_id": "SEU_CHAT_ID", "nome": "Seu Nome", "role": "admin", "senha": "sua_senha"}'
```

> ⚠️ O endpoint `/api/usuarios` requer autenticação JWT após o primeiro usuário ser criado.
> Para o primeiro admin, pode-se inserir diretamente no banco:
> ```bash
> docker compose exec postgres psql -U superguard -d superguard
> -- Na sessão psql:
> INSERT INTO usuarios (chat_id, nome, role, ativo, hashed_password)
> VALUES ('SEU_CHAT_ID', 'Admin', 'admin', true, 'hash_gerado_via_bcrypt');
> ```

### 6. Execute os testes

```bash
# Instale as dependências de desenvolvimento
pip install -r requirements.txt

# Execute todos os testes
cd superguard
pytest tests/ -v

# Testes específicos
pytest tests/test_detector.py -v
pytest tests/test_tracker.py -v
pytest tests/test_telegram_mock.py -v
```

---

## 🖥️ Deploy em Produção (VPS Barata)

### Recomendação de VPS

| Provedor | Plano | Preço/mês | Adequado para |
|----------|-------|-----------|---------------|
| Hetzner | CX21 | ~€4 | Até 4 câmeras (CPU) |
| DigitalOcean | Basic Droplet | ~$6 | Até 4 câmeras (CPU) |
| Oracle Cloud | VM.Standard.E2.1.Micro | **Grátis** | Teste / 1-2 câmeras |

### Passos de Deploy

```bash
# 1. Conecte à VPS
ssh root@seu-ip

# 2. Instale Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker $USER

# 3. Clone o repositório
git clone <url-do-repo> /opt/superguard
cd /opt/superguard/superguard

# 4. Configure o .env (mesmos passos acima)
cp .env.example .env
nano .env

# 5. Suba os serviços em modo produção
docker compose up --build -d

# 6. Configure reinício automático
# Já está configurado com restart: unless-stopped no docker-compose.yml

# 7. (Opcional) Configure nginx como proxy reverso
# para servir em HTTPS na porta 443
apt install nginx certbot python3-certbot-nginx
```

### Nginx + SSL (opcional mas recomendado)

```nginx
server {
    server_name seu-dominio.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
certbot --nginx -d seu-dominio.com
```

### Monitoramento de saúde

```bash
# Status dos containers
docker compose ps

# Health check da API
curl http://localhost:8000/health

# Logs em tempo real
docker compose logs -f --tail=100
```

---

## 🤖 Configuração do Bot Telegram

1. Acesse [@BotFather](https://t.me/botfather) no Telegram
2. Envie `/newbot` e siga as instruções
3. Copie o token gerado para `TELEGRAM_BOT_TOKEN` no `.env`
4. Descubra seu `chat_id` com [@userinfobot](https://t.me/userinfobot)
5. Defina esse ID em `TELEGRAM_ADMIN_CHAT_ID` no `.env`

---

## 📱 Comandos do Bot

| Comando | Acesso | Descrição |
|---------|--------|-----------|
| `/start` | Todos | Boas-vindas |
| `/registrar` | Não cadastrados | Solicita acesso ao sistema |
| `/status` | Cadastrados | Status atual do sistema |
| `/cameras` | Cadastrados | Lista câmeras ativas |
| `/ajuda` | Todos | Lista de comandos |
| `/usuarios` | Admin | Lista usuários cadastrados |
| `/adduser <id> <nome> [role]` | Admin | Adiciona/aprova usuário |
| `/removeuser <id>` | Admin | Desativa usuário |

---

## 🌐 API REST

A documentação interativa está disponível em:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Endpoints principais

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/auth/login` | Login JWT |
| `GET` | `/health` | Health check |
| `GET` | `/api/alertas` | Lista alertas (paginado) |
| `GET` | `/api/cameras` | Lista câmeras |
| `POST` | `/api/cameras` | Adiciona câmera (admin) |
| `GET` | `/api/usuarios` | Lista usuários (admin) |
| `POST` | `/api/usuarios` | Adiciona usuário (admin) |

---

## 🧠 Treinamento/Fine-tuning do Modelo

### Por que fazer fine-tuning?

O modelo `yolo11n.pt` pré-treinado no COCO detecta pessoas e objetos gerais,
mas pode ter menos precisão em cenários de supermercado específicos
(iluminação artificial, ângulos de câmera, produtos específicos).

### Passo a passo

#### 1. Coletar dados do seu supermercado

```bash
# Extraia frames das câmeras
ffmpeg -i rtsp://... -vf fps=1 frames/frame_%04d.jpg
```

#### 2. Anotar com Roboflow (recomendado)

1. Acesse [roboflow.com](https://roboflow.com) (plano gratuito disponível)
2. Crie projeto do tipo "Object Detection"
3. Faça upload dos frames coletados
4. Anote as classes: `pessoa`, `mochila`, `bolsa`, `produto_mao`, `comportamento_suspeito`
5. Exporte no formato **YOLOv11** (ou YOLO ultralytics)

#### 3. Treinar

```python
from ultralytics import YOLO

# Carrega modelo base
model = YOLO("yolo11n.pt")

# Treina com seus dados
results = model.train(
    data="path/to/dataset.yaml",
    epochs=100,
    imgsz=640,
    batch=16,
    device="cpu",          # ou "0" para GPU
    patience=20,           # early stopping
    name="superguard_v1",
    project="runs/train",
)

# Modelo treinado estará em: runs/train/superguard_v1/weights/best.pt
```

#### 4. Usar o modelo treinado

No `.env`:
```env
# Aponte para o modelo treinado
YOLO_MODEL_PATH=./models/superguard_v1_best.pt
```

No `app/cv/main.py`, ajuste:
```python
detector = DetectorFurto(
    modelo_path="./models/superguard_v1_best.pt",
    confianca_minima=settings.detection_confidence,
)
```

### Dicas para melhorar a precisão

- **Diversidade**: colete frames em diferentes horários (manhã, tarde, noite)
- **Balance**: pelo menos 200 imagens por classe
- **Augmentação**: Roboflow oferece augmentação automática (flip, brilho, rotação)
- **Validação**: reserve 20% dos dados para validação
- **Iteração**: comece com `yolo11n.pt` (nano, mais rápido) e escale para `yolo11s.pt` ou `yolo11m.pt` se precisar de mais precisão

---

## ⚙️ Suposições e Decisões de Design

1. **Modelo YOLO**: Usado `yolo11n.pt` (YOLOv11 Nano) como padrão — leve, rápido em CPU, disponível via Ultralytics. Pode ser substituído por qualquer modelo `.pt` treinado.

2. **Armazenamento**: Apenas frames de alertas são salvos (não vídeos), em conformidade com LGPD/GDPR. Os arquivos ficam em `/app/alerts/` compartilhado entre os serviços.

3. **Debounce**: 30 segundos por câmera para evitar spam de alertas do mesmo evento.

4. **CPU Fallback**: Ultralytics detecta automaticamente se há GPU disponível. O sistema funciona inteiramente em CPU (mais lento, mas funcional).

5. **Autenticação**: JWT simples para o painel web. Bot Telegram usa chat_id como identificador único.

6. **HTMX**: Interface web usa HTMX + Tailwind CSS servidos via CDN — sem necessidade de Node.js ou build step.

7. **Threading**: Um thread por câmera para processamento paralelo. Cada thread tem seu próprio estado de rastreamento e debounce.

8. **Comunicação interna**: Worker CV → API via HTTP com chave secreta no header (`X-Worker-Key`). Alternativa mais robusta seria Redis/RabbitMQ, mas HTTP é suficiente para a escala proposta.

---

## 🔒 Segurança e Privacidade (LGPD/GDPR)

- ✅ Não grava vídeos completos — apenas frames de eventos suspeitos
- ✅ Fotos de alertas são sobrescritas/removidas pelo admin
- ✅ Acesso ao painel via JWT com expiração configurável
- ✅ Bot Telegram só envia alertas para usuários explicitamente cadastrados
- ✅ Senhas com hash bcrypt (nunca armazenadas em texto plano)
- ✅ Variáveis sensíveis em `.env` (nunca no código-fonte)

---

## 📊 Performance Estimada

| Hardware | Câmeras | FPS/câmera | GPU |
|----------|---------|------------|-----|
| Intel i5 / 8GB RAM | 2-4 | 10-15 FPS | Não |
| NVIDIA GTX 1060 | 4-8 | 20-30 FPS | Sim |
| Raspberry Pi 4 | 1-2 | 5-8 FPS | Não |
| VPS Hetzner CX21 | 2-3 | 8-12 FPS | Não |

---

*SuperGuard v1.0 — Desenvolvido com Python 3.12, FastAPI, Ultralytics YOLO e python-telegram-bot*

---

## ⚙️ Abrindo o Projeto no PyCharm

Esta seção explica, passo a passo, como clonar e configurar o **SuperGuard** no **PyCharm Community** ou **Professional** (versões 2023.x ou superior).

### Pré-requisitos locais

| Ferramenta | Versão mínima | Download |
|------------|--------------|---------|
| Python | 3.12 | [python.org](https://www.python.org/downloads/) |
| PyCharm | 2023.1 | [jetbrains.com/pycharm](https://www.jetbrains.com/pycharm/download/) |
| Git | Qualquer | [git-scm.com](https://git-scm.com/) |
| Docker Desktop *(opcional)* | 24+ | [docker.com](https://www.docker.com/products/docker-desktop/) |

> **Nota:** O PostgreSQL e os serviços Docker são **opcionais** para desenvolver e testar localmente.
> Os testes unitários não precisam de banco nem de câmera.

---

### Passo 1 — Clonar o repositório

**Opção A — via PyCharm (VCS integrado)**

1. Abra o PyCharm
2. Na tela de boas-vindas clique em **Get from VCS**
   (ou no menu: **File → New Project from Version Control**)
3. Cole a URL do repositório:
   ```
   https://github.com/edldna/edldna.git
   ```
4. Escolha o diretório local (ex: `C:\Projetos\edldna` ou `~/projetos/edldna`)
5. Clique em **Clone**

**Opção B — via terminal Git**

```bash
# Clona o repositório na pasta de sua preferência
git clone https://github.com/edldna/edldna.git
cd edldna
```

---

### Passo 2 — Abrir a pasta `superguard` no PyCharm

O projeto SuperGuard fica dentro da subpasta `superguard/`.
Precisamos dizer ao PyCharm que **essa** é a raiz do projeto Python.

1. No PyCharm, vá em **File → Open...**
2. Navegue até a pasta clonada e selecione a subpasta **`superguard`**
3. Clique em **OK** → se perguntado "Open in New Window?", escolha **New Window** (ou **This Window**)

> O PyCharm detectará automaticamente o arquivo `pyproject.toml` na raiz de `superguard/`
> e reconhecerá o projeto como Python.

---

### Passo 3 — Criar e configurar o ambiente virtual (venv)

1. Vá em **File → Settings** (Windows/Linux) ou **PyCharm → Preferences** (macOS)
2. Navegue até **Project: superguard → Python Interpreter**
3. Clique no ícone de engrenagem ⚙️ → **Add Interpreter → Add Local Interpreter...**
4. Selecione **Virtualenv Environment**
   - Location: `superguard/.venv` (ou outro caminho de sua preferência)
   - Base Interpreter: selecione **Python 3.12**
5. Marque **"Inherit global site-packages"** apenas se quiser herdar pacotes globais
6. Clique em **OK**

---

### Passo 4 — Instalar as dependências

Abra o **Terminal integrado** do PyCharm (**View → Tool Windows → Terminal** ou `Alt+F12`):

```bash
# Ativa o ambiente virtual (se não estiver ativado automaticamente)
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Instala todas as dependências do projeto
pip install -r requirements.txt

# Ou instala via pyproject.toml (inclui deps de desenvolvimento como pytest):
pip install -e ".[dev]"
```

> 💡 O PyCharm mostrará uma notificação no topo do editor oferecendo instalar
> automaticamente os pacotes — clique em **Install** para usar essa facilidade.

---

### Passo 5 — Configurar o arquivo `.env`

O projeto usa variáveis de ambiente. Crie seu `.env` a partir do exemplo:

```bash
# No terminal do PyCharm:
cp .env.example .env
```

Edite o arquivo `.env` diretamente no PyCharm e preencha pelo menos:

```env
TELEGRAM_BOT_TOKEN=SEU_TOKEN_AQUI
TELEGRAM_ADMIN_CHAT_ID=SEU_CHAT_ID
POSTGRES_PASSWORD=uma_senha_segura
SECRET_KEY=chave_aleatoria_de_32_chars
CAMERA_URLS=rtsp://192.168.1.100:554/stream
```

> 💡 Para gerar `SECRET_KEY`, use o terminal integrado:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

---

### Passo 6 — Configurar o Test Runner (pytest)

O PyCharm detecta automaticamente o `pytest` configurado em `pyproject.toml`.
Para confirmar:

1. **File → Settings → Tools → Python Integrated Tools**
2. **Default test runner**: selecione **pytest**
3. **Working directory**: certifique-se de apontar para `superguard/`
4. Clique em **OK**

Para rodar os testes:
- Abra qualquer arquivo `tests/test_*.py`
- Clique no ícone ▶ verde ao lado de qualquer função de teste
- Ou clique com botão direito na pasta `tests/` → **Run 'pytest in tests'**

Todos os **21 testes** devem passar sem precisar de câmera, banco ou Telegram:

```
tests/test_detector.py       9 testes ✅
tests/test_tracker.py        7 testes ✅
tests/test_telegram_mock.py  5 testes ✅
```

---

### Passo 7 — Executar a API localmente (sem Docker)

Para rodar a API FastAPI direto no PyCharm:

1. Vá em **Run → Edit Configurations...**
2. Clique no **+** → **Python**
3. Configure:
   - **Name**: `SuperGuard API`
   - **Module name**: `uvicorn`
   - **Parameters**: `app.api.main:app --reload --host 0.0.0.0 --port 8000`
   - **Working directory**: selecione a pasta `superguard/`
   - **Environment variables**: marque **"Load .env file"** ou adicione as variáveis manualmente
4. Clique em **OK** e pressione ▶ para iniciar

A API estará disponível em: **http://localhost:8000**
Documentação interativa: **http://localhost:8000/docs**

---

### Passo 8 — Executar os Workers (CV e Bot Telegram)

**Worker de Visão Computacional:**

1. **Run → Edit Configurations... → +  → Python**
2. Configure:
   - **Name**: `SuperGuard CV Worker`
   - **Module name**: `app.cv.main`
   - **Working directory**: pasta `superguard/`
3. Salve e execute com ▶

**Bot Telegram (modo polling):**

O bot sobe automaticamente junto com a API (veja `app/api/main.py`, função `lifespan`).
Para rodá-lo de forma independente:

1. **Run → Edit Configurations... → + → Python**
2. Configure:
   - **Name**: `SuperGuard Bot`
   - **Module name**: `app.bot.telegram_bot`
   - **Working directory**: pasta `superguard/`
3. Execute com ▶

---

### Passo 9 — Subir tudo com Docker (recomendado para produção)

Se preferir usar o Docker Compose diretamente pelo PyCharm:

1. Instale o plugin **Docker** (caso não esteja instalado):
   **File → Settings → Plugins** → busque "Docker" → **Install**
2. Certifique-se de que o **Docker Desktop** está rodando
3. Abra o arquivo `docker-compose.yml` no PyCharm
4. Clique no ícone ▶▶ (duplo play) ao lado de `services:` para subir todos os serviços

Ou pelo terminal integrado:
```bash
# Na pasta superguard/
docker compose up --build
```

---

### Estrutura de Run Configurations recomendada no PyCharm

```
Run/Debug Configurations
├── 🟢 SuperGuard API          (uvicorn app.api.main:app --reload)
├── 🟢 SuperGuard CV Worker    (python -m app.cv.main)
├── 🟢 SuperGuard Bot          (python -m app.bot.telegram_bot)
└── 🧪 pytest (tests/)         (pytest tests/ -v)
```

---

### Dicas extras do PyCharm para este projeto

| Recurso | Como acessar |
|---------|-------------|
| Completar código FastAPI | Instale o plugin **FastAPI** em Settings → Plugins |
| Inspecionar modelos SQLAlchemy | **Database** tool window → conecte com as credenciais do `.env` |
| Ver logs em tempo real | **Run** tool window → aba **Console** |
| Debugar com breakpoints | Clique na margem esquerda do editor → ícone 🐛 (Debug) em vez de ▶ |
| Formatar código automaticamente | `Ctrl+Alt+L` (Windows/Linux) ou `⌥⌘L` (macOS) |
| Busca global | `Shift+Shift` (Search Everywhere) |
| Estrutura do projeto | `Alt+1` abre o painel **Project** |
| Verificação de tipos | Instale o plugin **Mypy** e aponte para `superguard/` |

---

### Problemas comuns

**Erro: `ModuleNotFoundError: No module named 'app'`**
> O diretório de trabalho está errado. Verifique em Run Configuration → **Working directory** → deve apontar para `superguard/`.

**Erro: `ModuleNotFoundError: No module named 'ultralytics'`**
> As dependências não foram instaladas. Rode `pip install -r requirements.txt` no terminal integrado com o venv ativado.

**PyCharm não encontra o intérprete**
> Vá em **File → Settings → Python Interpreter** e selecione manualmente `.venv/bin/python` (Linux/Mac) ou `.venv\Scripts\python.exe` (Windows).

**Erro de banco de dados ao subir a API sem Docker**
> Sem o PostgreSQL rodando localmente, a API não conectará ao banco.
> Para testar somente os endpoints, suba o postgres via Docker:
> ```bash
> docker compose up postgres -d
> ```
> E rode a API diretamente no PyCharm.

**Bot Telegram não conecta**
> Verifique se `TELEGRAM_BOT_TOKEN` está correto no `.env`.
> Teste com:
> ```bash
> curl https://api.telegram.org/bot<SEU_TOKEN>/getMe
> ```

