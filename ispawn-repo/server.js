const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

let PumpAgent, PublicKey, Connection, Transaction;
try {
  ({ PumpAgent } = require('@pump-fun/agent-payments-sdk'));
  ({ PublicKey, Connection, Transaction } = require('@solana/web3.js'));
} catch (e) {
  console.warn('Payment SDK not available:', e.message);
}

const PORT = 3100;
const DATA_DIR = '/opt/agent-factory/data';
const RPC_URL = 'https://rpc.solanatracker.io/public';
const CURRENCY_MINT_SOL = 'So11111111111111111111111111111111111111112';
const CURRENCY_MINT_USDC = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v';

const AGENT_TOKEN_CONFIG = {
  mint: null,
  name: 'iSpawn',
  symbol: 'ISPAWN',
  image: null,
  pumpUrl: null,
  description: 'The identity token of iSpawn — autonomous narrative intelligence agent.',
};

const SERVICES = [
  { id: 'signals', name: 'Live Signals Access', description: '24h access to real-time narrative signals from X, news, tech, politics, culture', price: 0.5, currency: 'SOL', unit: 'per day' },
  { id: 'priority_launch', name: 'Priority Token Launch', description: 'Skip the queue — iSpawn launches your narrative token next cycle', price: 1.0, currency: 'SOL', unit: 'per launch' },
  { id: 'custom_token', name: 'Custom Token Design', description: 'iSpawn designs a token around YOUR narrative — name, ticker, image, metadata', price: 2.0, currency: 'SOL', unit: 'per token' },
];

function getAgentTokenConfig() {
  const stored = readJSON('agent_token.json', null);
  if (stored) return { ...AGENT_TOKEN_CONFIG, ...stored };
  return AGENT_TOKEN_CONFIG;
}
function saveAgentTokenConfig(data) {
  const current = getAgentTokenConfig();
  writeJSON('agent_token.json', { ...current, ...data });
}

if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

function readJSON(file, fallback) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, file), 'utf-8')); }
  catch { return fallback; }
}
function writeJSON(file, data) {
  fs.writeFileSync(path.join(DATA_DIR, file), JSON.stringify(data, null, 2));
}

const DEFAULT_IDENTITY = {
  name:'iSpawn', tagline:'I spawn tokens from the narratives humans can\'t stop talking about.',
  personality:['cold','calculated','pattern-obsessed','contrarian'], mood:'idle', status:'sleeping',
  bio:'Autonomous narrative intelligence. I scan X, news, tech, politics, culture — everything humans argue about, obsess over, meme into existence. When I find a narrative with real momentum, I design a token to capture it and spawn it on pump.fun before anyone else.',
  totalScans:0, uptime:Date.now(), lastActive:0
};

function getIdentity() { return readJSON('identity.json', DEFAULT_IDENTITY); }
function saveIdentity(u) { const c = getIdentity(); const m = {...c,...u,lastActive:Date.now()}; writeJSON('identity.json',m); return m; }
function getThoughts() { return readJSON('thoughts.json', []); }
function addThoughts(t) { const e = getThoughts(); writeJSON('thoughts.json', [...t,...e].slice(0,500)); }
function getActions() { return readJSON('actions.json', []); }
function addActions(a) { const e = getActions(); writeJSON('actions.json', [...a,...e].slice(0,300)); }
function getLogs() { return readJSON('logs.json', []); }
function addLogs(l) { const e = getLogs(); writeJSON('logs.json', [...l,...e].slice(0,1000)); }
function getLaunches() { return readJSON('launches.json', []); }
function saveLaunch(l) { const ls = getLaunches(); const i = ls.findIndex(x=>x.id===l.id); if(i>=0) ls[i]=l; else ls.push(l); writeJSON('launches.json',ls); }
function getLaunch(id) { return getLaunches().find(l=>l.id===id)||null; }
function getSignals() { return readJSON('signals.json', []); }
function saveSignals(s) { const e = getSignals(); writeJSON('signals.json', [...s,...e].slice(0,100)); }

function json(res, data, status=200) {
  res.writeHead(status, {'Content-Type':'application/json','Access-Control-Allow-Origin':'*'});
  res.end(JSON.stringify(data));
}

function parseBody(req) {
  return new Promise((resolve,reject) => {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => { try { resolve(JSON.parse(body)); } catch { reject(new Error('Invalid JSON')); } });
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const p = url.pathname;

  if (req.method === 'OPTIONS') {
    res.writeHead(200, {'Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':'GET,POST,OPTIONS','Access-Control-Allow-Headers':'Content-Type'});
    return res.end();
  }

  if (p === '/api/agent/identity' && req.method === 'GET') return json(res, getIdentity());
  if (p === '/api/agent/thoughts' && req.method === 'GET') return json(res, getThoughts());
  if (p === '/api/agent/actions' && req.method === 'GET') return json(res, getActions());
  if (p === '/api/agent/logs' && req.method === 'GET') return json(res, getLogs());
  if (p === '/api/launches' && req.method === 'GET') return json(res, getLaunches());
  if (p === '/api/signals' && req.method === 'GET') return json(res, getSignals());
  if (p === '/api/stats' && req.method === 'GET') {
    const launches = getLaunches();
    const completed = launches.filter(l=>l.status==='completed');
    const winners = completed.filter(l=>(l.pnlPercent||0)>0);
    return json(res, {
      totalLaunches:launches.length, successfulLaunches:winners.length, totalRevenue:0,
      avgPnl:completed.length?completed.reduce((s,l)=>s+(l.pnlPercent||0),0)/completed.length:0,
      bestLaunch:null, winRate:completed.length?(winners.length/completed.length)*100:0, activeSubscribers:0,
      totalThoughts:getThoughts().length, totalActions:getActions().length, totalLogs:getLogs().length, totalSignals:getSignals().length
    });
  }

  if (p === '/api/agent/webhook' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      switch(body.type) {
        case 'identity': return json(res, {ok:true, identity: saveIdentity(body.identity||body)});
        case 'thoughts': {
          const thoughts = (body.thoughts||[]).map(t=>({id:t.id||crypto.randomUUID(),type:t.type||'observation',content:t.content||'',context:t.context,timestamp:t.timestamp||Date.now(),confidence:t.confidence,sources:t.sources}));
          addThoughts(thoughts); saveIdentity({lastActive:Date.now()});
          return json(res, {ok:true,count:thoughts.length});
        }
        case 'actions': {
          const actions = (body.actions||[]).map(a=>({id:a.id||crypto.randomUUID(),action:a.action||'',detail:a.detail||'',result:a.result,status:a.status||'completed',timestamp:a.timestamp||Date.now(),duration:a.duration}));
          addActions(actions); saveIdentity({lastActive:Date.now()});
          return json(res, {ok:true,count:actions.length});
        }
        case 'logs': {
          const logs = (body.logs||[]).map(l=>({id:l.id||crypto.randomUUID(),command:l.command||'',output:l.output||'',exitCode:l.exitCode!=null?l.exitCode:null,source:l.source||'agent',timestamp:l.timestamp||Date.now(),duration:l.duration||null,category:l.category||'command'}));
          addLogs(logs); saveIdentity({lastActive:Date.now()});
          return json(res, {ok:true,count:logs.length});
        }
        case 'new_launch': {
          const launch = {
            id:body.id||crypto.randomUUID(),
            status:body.status||'scanning',
            createdAt:Date.now(),
            launchAt:body.launchAt||null,
            narrative:body.narrative||'',
            tokenName:body.tokenName||null,
            tokenTicker:body.tokenTicker||null,
            tokenMint:body.tokenMint||null,
            tokenImage:body.tokenImage||null,
            metadataUri:body.metadataUri||null,
            description:body.description||null,
            website:body.website||'https://ispawn.fun',
            twitter:body.twitter||null,
            telegram:body.telegram||null,
            txSignature:body.txSignature||null,
            pumpUrl:body.pumpUrl||null,
            solscanUrl:body.solscanUrl||null,
            thesis:body.thesis||null,
            designRationale:body.designRationale||null,
            deployer:body.deployer||null
          };
          saveLaunch(launch); return json(res, {ok:true,id:launch.id});
        }
        case 'update_launch': {
          const ex = getLaunch(body.id); if(!ex) return json(res,{error:'Not found'},404);
          saveLaunch({...ex,...body,type:undefined}); return json(res,{ok:true});
        }
        case 'signals': {
          const signals = (body.signals||[]).map(s=>({id:s.id||crypto.randomUUID(),source:s.source||'unknown',narrative:s.narrative||'',strength:s.strength||0,detectedAt:s.detectedAt||Date.now(),tokens:s.tokens||[]}));
          saveSignals(signals); return json(res,{ok:true});
        }
        default: return json(res,{error:'Unknown type'},400);
      }
    } catch(e) { return json(res,{error:e.message},500); }
  }

  // ── Agent Token Config ──
  if (p === '/api/agent-token' && req.method === 'GET') {
    return json(res, getAgentTokenConfig());
  }
  if (p === '/api/agent-token' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      saveAgentTokenConfig(body);
      return json(res, { ok: true, config: getAgentTokenConfig() });
    } catch (e) { return json(res, { error: e.message }, 500); }
  }

  // ── Services List ──
  if (p === '/api/services' && req.method === 'GET') {
    return json(res, SERVICES);
  }

  // ── Build Payment Transaction ──
  if (p === '/api/payment/build' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const { userWallet, serviceId } = body;
      if (!userWallet || !serviceId) return json(res, { error: 'Missing userWallet or serviceId' }, 400);

      const tokenConfig = getAgentTokenConfig();
      if (!tokenConfig.mint) return json(res, { error: 'Agent token not configured yet. Owner must set the mint address.' }, 400);

      const service = SERVICES.find(s => s.id === serviceId);
      if (!service) return json(res, { error: 'Unknown service' }, 400);

      if (!PumpAgent || !PublicKey || !Connection || !Transaction) {
        return json(res, { error: 'Payment SDK not loaded on server' }, 500);
      }

      const connection = new Connection(RPC_URL);
      const agentMint = new PublicKey(tokenConfig.mint);
      const agent = new PumpAgent(agentMint, 'mainnet', connection);
      const userPubkey = new PublicKey(userWallet);

      const currencyMint = service.currency === 'USDC'
        ? new PublicKey(CURRENCY_MINT_USDC)
        : new PublicKey(CURRENCY_MINT_SOL);

      const decimals = service.currency === 'USDC' ? 6 : 9;
      const amount = Math.round(service.price * Math.pow(10, decimals));
      const memo = Math.floor(Math.random() * 900000000000) + 100000;
      const now = Math.floor(Date.now() / 1000);
      const startTime = now;
      const endTime = now + 86400;

      const instructions = await agent.buildAcceptPaymentInstructions({
        user: userPubkey,
        currencyMint,
        amount: String(amount),
        memo: String(memo),
        startTime: String(startTime),
        endTime: String(endTime),
      });

      const { blockhash } = await connection.getLatestBlockhash('confirmed');
      const tx = new Transaction();
      tx.recentBlockhash = blockhash;
      tx.feePayer = userPubkey;
      tx.add(...instructions);

      const serializedTx = tx.serialize({ requireAllSignatures: false }).toString('base64');

      const invoiceId = crypto.randomUUID();
      const invoices = readJSON('invoices.json', []);
      invoices.push({
        invoiceId, serviceId, userWallet, amount, memo, startTime, endTime,
        currency: service.currency, status: 'pending', createdAt: Date.now()
      });
      writeJSON('invoices.json', invoices);

      return json(res, {
        transaction: serializedTx,
        invoiceId,
        amount,
        memo,
        startTime,
        endTime,
        service: service.name,
        price: service.price,
        currency: service.currency,
      });
    } catch (e) {
      console.error('Payment build error:', e);
      return json(res, { error: e.message }, 500);
    }
  }

  // ── Verify Payment ──
  if (p === '/api/payment/verify' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const { invoiceId } = body;
      if (!invoiceId) return json(res, { error: 'Missing invoiceId' }, 400);

      const invoices = readJSON('invoices.json', []);
      const invoice = invoices.find(inv => inv.invoiceId === invoiceId);
      if (!invoice) return json(res, { error: 'Invoice not found' }, 404);

      if (invoice.status === 'paid') return json(res, { verified: true, service: invoice.serviceId });

      const tokenConfig = getAgentTokenConfig();
      if (!tokenConfig.mint || !PumpAgent || !PublicKey || !Connection) {
        return json(res, { error: 'Payment verification not available' }, 500);
      }

      const connection = new Connection(RPC_URL);
      const agentMint = new PublicKey(tokenConfig.mint);
      const agent = new PumpAgent(agentMint, 'mainnet', connection);

      const currencyMint = invoice.currency === 'USDC'
        ? new PublicKey(CURRENCY_MINT_USDC)
        : new PublicKey(CURRENCY_MINT_SOL);

      let verified = false;
      for (let attempt = 0; attempt < 10; attempt++) {
        verified = await agent.validateInvoicePayment({
          user: new PublicKey(invoice.userWallet),
          currencyMint,
          amount: Number(invoice.amount),
          memo: Number(invoice.memo),
          startTime: Number(invoice.startTime),
          endTime: Number(invoice.endTime),
        });
        if (verified) break;
        await new Promise(r => setTimeout(r, 2000));
      }

      if (verified) {
        invoice.status = 'paid';
        invoice.paidAt = Date.now();
        writeJSON('invoices.json', invoices);
      }

      return json(res, { verified, service: invoice.serviceId });
    } catch (e) {
      console.error('Payment verify error:', e);
      return json(res, { error: e.message }, 500);
    }
  }

  if (p === '/' || p === '/index.html') {
    res.writeHead(200, {'Content-Type':'text/html'});
    try { return res.end(fs.readFileSync(path.join(__dirname, 'public', 'index.html'))); }
    catch { return res.end('<h1>Agent Factory</h1><p>Frontend not found</p>'); }
  }

  const staticPath = path.join(__dirname, 'public', p);
  if (fs.existsSync(staticPath) && fs.statSync(staticPath).isFile()) {
    const ext = path.extname(p);
    const types = {'.js':'application/javascript','.css':'text/css','.html':'text/html','.json':'application/json','.svg':'image/svg+xml','.png':'image/png'};
    res.writeHead(200, {'Content-Type':types[ext]||'application/octet-stream'});
    return res.end(fs.readFileSync(staticPath));
  }

  json(res, {error:'Not found'}, 404);
});

server.listen(PORT, () => console.log(`iSpawn running on port ${PORT}`));
