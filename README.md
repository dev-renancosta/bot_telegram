# Bot Telegram — Lista semanal de futebol (Python + SQLite)

Bot minimalista para grupos de futebol semanal: **uma única mensagem fixa** com botões inline para confirmar presença, atualizada em tempo real (sem spam no grupo).

## Requisitos
- Python **3.12+**
- Bot no Telegram com permissões no grupo (recomendado: **fixar mensagens**)

## Instalação (local)

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuração
Crie um arquivo `.env` baseado em `.env.example`.

- **BOT_TOKEN**: token do BotFather
- **GROUP_ID**: id numérico do grupo (ex.: `-1001234567890`)
- **GROUP_INVITE_LINK** (recomendado): link do grupo com **“Solicitar entrada”** habilitado (o botão do `/start` aponta para ele)
- **MAX_PLAYERS**: limite de jogadores na lista principal (default 15)
- **GAME_\***: dados do jogo (nome, dia, horário, local, endereço)
- **TZ**: timezone dos agendamentos (default `America/Sao_Paulo`)
- **ADMIN_IDS** (opcional): IDs numéricos para bootstrap de admins no banco
- **FINANCE_\***: configurações do módulo de mensalidades (PIX, admin financeiro, mês inicial)

## Executar

```bash
python main.py
```

## Deploy com Docker

```bash
docker compose up --build -d
```

## Deploy (Railway / Render / VPS)
**Railway/Render**: crie um serviço Docker ou Python, configure as variáveis do `.env` como environment variables e garanta persistência do `DB_PATH` (SQLite).

- **VPS**: use Docker Compose e monte volume para o arquivo `bot.db`.

### Dica importante (SQLite)
- Em Railway/Render, **garanta volume persistente**; caso contrário, o banco reinicia a cada deploy.

## Comandos
- **Admin**: `/criarlista`, `/apagarlista`, `/relatorio`
- **Público**: `/start`, `/status`, `/financeiro`

## Onboarding + aprovação automática do grupo
- Configure o grupo como **“Solicitar entrada”** (join request).
- Dê ao bot permissão/admin para **aprovar solicitações de entrada**.
- Fluxo:
  - Usuário envia `/start` no bot → onboarding em DM + botão “Solicitar entrada no grupo”.
  - Usuário solicita entrada → bot aprova automaticamente.
  - Ao aprovar, o sistema:
    - registra o usuário como **membro rastreável**
    - cria a mensalidade do **mês atual** com status **PENDENTE** (idempotente por `UNIQUE(player_id, year, month)`)

## Financeiro (mensalidades)
- O comando `/financeiro` pode ser enviado no grupo ou no privado; o bot **responde no privado**.
- Meses **ATRASADOS** aparecem como botões. Ao clicar, o bot mostra o valor e oferece um botão **PIX** que copia automaticamente (quando suportado).
- Ao enviar comprovante em DM (foto/PDF/documento), o bot salva apenas **metadata** (incluindo `file_id`) e encaminha ao `FINANCE_ADMIN_ID` com botões **✅ Aprovar** / **❌ Recusar**.

## Relatório financeiro (admin)
- `/relatorio`: painel administrativo no privado com:
  - pagos
  - inadimplentes (com detalhe por usuário, cobrar e marcar pago)
  - comprovantes pendentes (em análise)
  - estatísticas

## Cobrança automática
- Todo **5º dia útil** do mês (09:00), o bot envia DM automática para quem **não está PAGO** no mês atual.
- Anti-spam: registra envios em `cobranca_logs`.

## Automações
- Quarta 12:00: cria lista e fixa
- Quinta 12:00: lembrete
- Sexta 12:00: aviso do jogo
- Sexta 17:00: fecha lista (remove botões)

## Observações
- O bot tenta mandar DM quando alguém sai da espera e entra na lista principal. Se o usuário bloquear DM, o bot segue sem quebrar.
