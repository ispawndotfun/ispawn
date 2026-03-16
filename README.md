iSpawn
Autonomous agent that scans real-time narratives across the internet and launches tokens on pump.fun based on what it finds.

Live: ispawn.fun

What it does
iSpawn runs a continuous loop:

Scans five data streams every 10 minutes — X/Twitter, breaking news, tech, culture, politics
Accumulates signals throughout the day, scoring each by source reliability and narrative momentum
Picks one winner — after enough data (minimum 3 scans), selects the strongest signal
Launches a real token on pump.fun via PumpPortal's Lightning API — name, ticker, image, IPFS metadata, bonding curve, all on-chain
Posts everything to the dashboard in real time — thoughts, analysis, signals, launch status, transaction links
One token per day. No manual intervention. The agent decides what to launch and when.

Architecture
┌─────────────────────────────────────────────────┐
│                   go.py (daemon)                │
│                                                 │
│  every 10 min:                                  │
│    1. web search × 5 sources (via picoclaw)     │
│    2. score & accumulate signals                │
│    3. if ready → pick best → launcher_v2.py     │
│    4. push all state to server.js via webhook   │
│                                                 │
│  rules:                                         │
│    - min 3 scans before first launch            │
│    - max 1 launch per UTC day                   │
│    - signal strength threshold ≥ 0.7            │
│    - daily reset at midnight UTC                │
└──────────────────────┬──────────────────────────┘
                       │ HTTP POST webhooks
                       ▼
┌─────────────────────────────────────────────────┐
│               server.js (Node.js)               │
│                                                 │
│  serves:                                        │
│    - static frontend (public/index.html)        │
│    - REST API for agent state                   │
│    - payment endpoints (@pump-fun/agent-sdk)    │
│                                                 │
│  stores:                                        │
│    - thoughts, actions, logs (JSON files)        │
│    - signals, launches                          │
│    - agent identity & config                    │
│    - invoices for paid services                 │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│              launcher_v2.py                     │
│                                                 │
│  1. create PumpPortal Lightning wallet          │
│  2. transfer SOL from agent wallet              │
│  3. generate token image (PIL)                  │
│  4. upload name + symbol + image → pump.fun     │
│     IPFS (returns metadata URI)                 │
│  5. call PumpPortal Lightning API:              │
│     POST /api/trade?api-key={key}               │
│     action: "create"                            │
│     tokenMetadata: {name, symbol, uri}          │
│     mint: <new keypair>                         │
│  6. verify TX on-chain via getTransaction       │
│     (check meta.err === null)                   │
│  7. return mint address, TX sig, pump.fun URL   │
└─────────────────────────────────────────────────┘
Token launch flow (on-chain)
Each launch executes this Solana transaction:

#	Instruction	Purpose
1	ComputeBudget.SetComputeUnitLimit	400,000 CU budget
2	ComputeBudget.SetComputeUnitPrice	Priority fee for faster landing
3	SystemProgram.transfer	Jito tip (0.00035 SOL)
4	PumpFun.create_v2	Create token mint, bonding curve, ATA, metadata
The create_v2 instruction creates:

Token mint (Token-2022 program)
Bonding curve account
Associated token account for the curve
On-chain metadata pointer
Total cost per launch: ~0.022 SOL (rent for accounts + fees).

Dashboard
Single-page frontend with:

Agent identity card — name, mood, status, personality traits
Identity token — pinned section showing the agent's own pump.fun token (CA, image, links)
Services panel — paid services (signals access, priority launch, custom token design) via pump.fun's tokenized agents SDK
Spawned tokens — list view with image, name, ticker, CA, pump.fun/solscan links
Thought stream — real-time feed of the agent's observations, analysis, decisions
Live signals — scored narrative signals from all sources
Terminal — raw command logs
Wallet connect — Phantom integration for service payments
Dark mode — toggle between paper notebook light and dark themes
Payment integration
Uses @pump-fun/agent-payments-sdk for on-chain service payments:

User connects Phantom wallet
Selects a service (e.g. "Live Signals Access — 0.5 SOL")
Server builds payment TX via PumpAgent.buildAcceptPaymentInstructions()
User signs with Phantom, TX lands on Solana
Server verifies via PumpAgent.validateInvoicePayment()
Service activated
Each payment creates a unique Invoice ID PDA on-chain — no double payments, fully verifiable.

File structure
├── server.js              # Node.js HTTP server + API + payment endpoints
├── public/
│   ├── index.html         # Dashboard frontend (vanilla JS, no framework)
│   ├── favicon.ico        # iS logo
│   ├── logo.png           # 512px logo
│   └── logo-192.png       # Mobile icon
├── agent/
│   ├── go.py              # Main daemon — scan loop, signal accumulation, launch decision
│   └── launcher_v2.py     # Pump.fun token launcher via PumpPortal Lightning API
└── docs/
    └── ARCHITECTURE.md    # This document in detail
Environment variables
# Agent daemon (go.py)
ISPAWN_SERVER_IP=         # Server IP
ISPAWN_SERVER_USER=       # SSH user
ISPAWN_SERVER_PASS=       # SSH password
OPENROUTER_API_KEY=       # For LLM-powered web search via picoclaw

# Token launcher (launcher_v2.py)
SOLANA_PRIVATE_KEY=       # Agent wallet private key (base58)

# Server (server.js) — set in the process environment
AGENT_TOKEN_MINT_ADDRESS= # Agent's own pump.fun token mint
Running
# 1. Start the dashboard server
cd /opt/agent-factory
node server.js

# 2. Start the agent daemon
python3 agent/go.py
The agent scans every 10 minutes and the dashboard updates in real time via polling.

Dependencies
Server (Node.js):

@pump-fun/agent-payments-sdk — pump.fun tokenized agent payments
@solana/web3.js — Solana transaction building
Agent (Python):

paramiko — SSH to server
solders — Solana transaction construction and signing
requests — HTTP calls to PumpPortal API and Solana RPC
Pillow — Token image generation
License
MIT
