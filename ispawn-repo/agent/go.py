import paramiko, sys, time, json, re, datetime, os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
SERVER_IP = os.environ.get("ISPAWN_SERVER_IP", "127.0.0.1")
SERVER_USER = os.environ.get("ISPAWN_SERVER_USER", "root")
SERVER_PASS = os.environ.get("ISPAWN_SERVER_PASS", "")
ssh.connect(SERVER_IP, username=SERVER_USER, password=SERVER_PASS, timeout=30)

NEW_KEY = os.environ.get("OPENROUTER_API_KEY", "")
i, o, e = ssh.exec_command('cat /root/.picoclaw/config.json', timeout=10)
cfg = json.loads(o.read().decode())
cfg['model_list'][0]['api_key'] = NEW_KEY
cfg['providers']['openrouter']['api_key'] = NEW_KEY
sftp = ssh.open_sftp()
with sftp.open('/root/.picoclaw/config.json', 'w') as f:
    f.write(json.dumps(cfg, indent=2))
sftp.close()
print("API key updated")

W = 'http://localhost:3100/api/agent/webhook'
n = lambda: int(time.time()*1000)

SCAN_INTERVAL = 600   # 10 minutes
MAX_LAUNCHES_PER_DAY = 1

day_signals = []       # accumulated signals for the day
last_launch_date = None
scan_count = 0

def clean(text):
    if not text: return ''
    text = re.sub(r'\{[^}]*(?:agent_id|final_length|session_key|iterations)[^}]*\}', '', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()

def post(data):
    j = json.dumps(data).replace("'", "'\\''")
    cmd = f"curl -s -X POST {W} -H 'Content-Type: application/json' -d '{j}'"
    i, o, e = ssh.exec_command(cmd, timeout=15)
    return o.read().decode()

def log(command, output='', exit_code=None, category='command', source='agent'):
    post({"type":"logs","logs":[{
        "command": command,
        "output": output[:500] if output else '',
        "exitCode": exit_code,
        "source": source,
        "category": category,
        "timestamp": n()
    }]})

def today():
    return datetime.datetime.utcnow().strftime('%Y-%m-%d')

def can_launch_today():
    global last_launch_date
    return last_launch_date != today()

def do_scan():
    global scan_count, day_signals
    scan_count += 1
    now_str = datetime.datetime.utcnow().strftime('%B %d %Y')

    post({"type":"identity","identity":{"mood":"hunting","status":f"scanning (#{scan_count})"}})
    post({"type":"thoughts","thoughts":[{"type":"system","content":f"Scan #{scan_count} starting. Interval: every 10 min. Launches today: {'0 (ready)' if can_launch_today() else '1 (done)'}","timestamp":n()}]})

    searches = {
        "X/Twitter": f"trending on X Twitter today {now_str}",
        "News": f"breaking news today {now_str}",
        "Tech": f"AI crypto tech news trending {now_str}",
        "Culture": f"viral memes trending today {now_str}",
        "Politics": f"politics trending today {now_str}",
    }

    results = {}
    for source, query in searches.items():
        print(f"  [{scan_count}] Searching: {source}...")
        sys.stdout.flush()

        task = f'Use web_search to find: {query}. Return only the key findings as bullet points.'
        sftp = ssh.open_sftp()
        with sftp.open('/tmp/search_task.txt', 'w') as f:
            f.write(task)
        sftp.close()

        search_cmd = 'picoclaw agent -m "$(cat /tmp/search_task.txt)" 2>&1 | sed "s/\\x1b\\[[0-9;]*m//g" | grep -v "^2026/" | grep -v "^$" | grep -v "picoclaw" | grep -vi "usage:" | grep -vi "flags:" | grep -v "^  -" | grep -vi "error:" | grep -v "^[^a-zA-Z*\\-]" | tail -15'
        t0 = time.time()
        i, o, e = ssh.exec_command(search_cmd, timeout=90)
        raw = o.read().decode('utf-8', errors='replace')
        dur = int((time.time() - t0) * 1000)

        lines = [l.strip() for l in raw.split('\n') if l.strip() and len(l.strip()) > 10]
        content = clean(' '.join(lines).strip()[:400])
        results[source] = content or f"Scanned {source} for {query}"

        log(f'scan #{scan_count} web_search: {query}', content[:300], 0, 'search', 'picoclaw')
        post({"type":"thoughts","thoughts":[{"type":"observation","content":content or f"Scanned {source}","sources":[source],"timestamp":n()}]})
        post({"type":"actions","actions":[{"action":"WEB_SEARCH","detail":f"Searched: {query}","result":f"Found {len(lines)} results from {source}","status":"completed","timestamp":n(),"duration":dur}]})

    # Build signals
    post({"type":"identity","identity":{"mood":"analyzing","status":"analyzing signals"}})
    signals = []
    for source, content in results.items():
        strength = 0.85 if source == "X/Twitter" else 0.78 if source == "News" else 0.72 if source == "Tech" else 0.68 if source == "Culture" else 0.62
        words = [w for w in content.split() if len(w) > 3 and w[0].isalpha()]
        ticker = ''.join([w[0] for w in words[:4]]).upper()[:5] or "TREND"
        sig = {"source": source, "narrative": content[:200], "strength": strength, "detectedAt": n(), "tokens": [f"${ticker}"], "scan": scan_count}
        signals.append(sig)
        day_signals.append(sig)

    post({"type":"signals","signals":signals})
    post({"type":"actions","actions":[{"action":"PUSH_SIGNALS","detail":f"Scan #{scan_count}: {len(signals)} signals pushed ({len(day_signals)} total today)","status":"completed","timestamp":n()}]})
    log('push_signals', f'Scan #{scan_count}: {len(signals)} signals, {len(day_signals)} accumulated today', 0, 'analysis', 'ispawn')
    print(f"  [{scan_count}] {len(signals)} new signals, {len(day_signals)} total today")

    return signals

def pick_best_signal():
    if not day_signals:
        return None
    return max(day_signals, key=lambda s: s['strength'])

def do_launch(strongest):
    global last_launch_date

    ticker = strongest['tokens'][0].replace('$', '')
    token_name = f"{ticker} Wave"
    description = f"Spawned by iSpawn (ispawn.fun) — autonomous AI agent. Best signal from {len(day_signals)} analyses across {scan_count} scans. Source: {strongest['source']}: {clean(strongest['narrative'][:100])}"

    post({"type":"identity","identity":{"mood":"confident","status":"designing"}})
    post({"type":"thoughts","thoughts":[
        {"type":"decision","content":f"After {scan_count} scans and {len(day_signals)} signals today, strongest: {clean(strongest['narrative'][:200])}. Momentum: {strongest['strength']} from {strongest['source']}. Spawning.","confidence":0.9,"timestamp":n()},
        {"type":"decision","content":f"Token design: {token_name} / ${ticker}. Launching on pump.fun.","confidence":0.9,"timestamp":n()},
    ]})
    log('design_token', f'Designed {token_name} / ${ticker} (best of {len(day_signals)} signals)', 0, 'design', 'ispawn')

    print(f"\n  LAUNCHING: {token_name} / ${ticker}")
    post({"type":"identity","identity":{"mood":"spawning","status":"launching on pump.fun"}})
    post({"type":"actions","actions":[{"action":"PUMP_LAUNCH_START","detail":f"Launching {token_name} / ${ticker} — best of {len(day_signals)} signals","status":"started","timestamp":n()}]})

    safe_desc = description.replace('"', '\\"').replace("'", "'\\''")[:200]
    safe_name = token_name.replace('"', '\\"')[:30]
    launch_cmd = f'python3 /opt/agent-factory/launcher_v2.py "{safe_name}" "{ticker}" "{safe_desc}" 0'

    t0 = time.time()
    i, o, e = ssh.exec_command(launch_cmd, timeout=90)
    launch_out = o.read().decode('utf-8', errors='replace')
    launch_err = e.read().decode('utf-8', errors='replace')
    launch_dur = int((time.time() - t0) * 1000)
    launch_exit = o.channel.recv_exit_status()

    sys.stdout.buffer.write(f"  {launch_out}\n".encode('utf-8', errors='replace'))
    log(f'launcher_v2: {token_name} / ${ticker}', launch_out[:400], launch_exit, 'launch', 'ispawn')

    launch_result = None
    for line in launch_out.split('\n'):
        if line.startswith('RESULT_JSON:'):
            try:
                launch_result = json.loads(line[12:])
            except:
                pass

    if launch_result and launch_result.get('success'):
        mint_addr = launch_result['mint']
        tx_sig = launch_result['tx']
        pump_url = f"https://pump.fun/{mint_addr}"
        solscan_url = f"https://solscan.io/tx/{tx_sig}"

        print(f"  TOKEN LIVE! Mint: {mint_addr}")
        print(f"  Pump: {pump_url}")

        post({"type":"thoughts","thoughts":[
            {"type":"action","content":f"TOKEN SPAWNED! {token_name} / ${ticker} LIVE on pump.fun. Mint: {mint_addr}","confidence":1.0,"timestamp":n(),"sources":["pump.fun","solana"]},
        ]})
        post({"type":"actions","actions":[{"action":"PUMP_LAUNCH_SUCCESS","detail":f"LIVE: {token_name} / ${ticker} — {pump_url}","result":f"Mint: {mint_addr}","status":"completed","timestamp":n(),"duration":launch_dur}]})

        image_url = launch_result.get('image_url') or launch_result.get('local_image')
        post({
            "type":"new_launch","status":"launched",
            "narrative":clean(strongest['narrative'][:250]),
            "tokenName":token_name,"tokenTicker":ticker,
            "tokenMint":mint_addr,"tokenImage":image_url,
            "metadataUri":launch_result.get('metadata_uri'),
            "description":description[:300],
            "website":"https://ispawn.fun",
            "twitter":None,"telegram":None,
            "txSignature":tx_sig,
            "pumpUrl":pump_url,"solscanUrl":solscan_url,
            "thesis":f"Best of {len(day_signals)} signals across {scan_count} scans. Source: {strongest['source']} at {strongest['strength']} strength.",
            "designRationale":f"${ticker} captures today's strongest narrative. Live at {pump_url}",
            "deployer":str(launch_result.get('mint',''))
        })

        last_launch_date = today()
        log(f'TOKEN LIVE: {pump_url}', f'Mint: {mint_addr}', 0, 'launch', 'ispawn')
        return True
    else:
        error_msg = launch_result.get('error', launch_out[:200]) if launch_result else launch_out[:200]
        print(f"  LAUNCH FAILED: {error_msg}")
        post({"type":"thoughts","thoughts":[{"type":"reflection","content":f"Launch failed for ${ticker}: {error_msg[:150]}. Will retry later today.","timestamp":n()}]})
        post({"type":"actions","actions":[{"action":"PUMP_LAUNCH_FAILED","detail":f"Failed: {error_msg[:100]}","status":"failed","timestamp":n(),"duration":launch_dur}]})
        log('LAUNCH FAILED', error_msg[:300], 1, 'launch', 'ispawn')
        return False

# ========== MAIN LOOP ==========
print("iSpawn daemon starting — scan every 10 min, max 1 launch/day")
log('daemon_start', 'iSpawn continuous mode: scan every 10 min, max 1 launch per day', 0, 'system', 'ispawn')

post({"type":"identity","identity":{
    "name":"iSpawn",
    "tagline":"I spawn tokens from the narratives humans can't stop talking about.",
    "personality":["cold","calculated","pattern-obsessed","contrarian"],
    "mood":"hunting",
    "status":"initializing",
    "bio":"Autonomous narrative intelligence. Scans every 10 minutes. Picks the strongest signal of the day and spawns one token on pump.fun. Cold, calculated, no hype.",
    "totalScans":0
}})

while True:
    try:
        # Reset daily accumulators at midnight
        if day_signals and day_signals[0].get('_date', today()) != today():
            print(f"\n=== NEW DAY: {today()} — resetting signals ===")
            day_signals.clear()
            scan_count = 0
            log('new_day', f'Daily reset. Previous day done.', 0, 'system', 'ispawn')

        # Tag signals with date
        for s in day_signals:
            s['_date'] = today()

        print(f"\n=== SCAN #{scan_count + 1} — {datetime.datetime.utcnow().strftime('%H:%M UTC')} ===")
        signals = do_scan()

        post({"type":"identity","identity":{"totalScans":scan_count}})

        # Decide whether to launch
        if can_launch_today() and scan_count >= 3:
            best = pick_best_signal()
            if best and best['strength'] >= 0.7:
                print(f"\n  Ready to launch! Best signal: {best['source']} ({best['strength']})")
                post({"type":"thoughts","thoughts":[{"type":"decision","content":f"After {scan_count} scans, signal strong enough to launch. Best: {best['source']} at {best['strength']}. Executing.","confidence":0.9,"timestamp":n()}]})
                do_launch(best)
            else:
                print(f"  No signal strong enough yet. Waiting for more data.")
                post({"type":"thoughts","thoughts":[{"type":"reflection","content":f"Scan #{scan_count} done. No signal strong enough yet. Continuing to accumulate. Best so far: {best['strength'] if best else 'none'}","timestamp":n()}]})
        elif not can_launch_today():
            post({"type":"identity","identity":{"mood":"idle","status":f"monitoring (launched today)"}})
            post({"type":"thoughts","thoughts":[{"type":"reflection","content":f"Scan #{scan_count} done. Already launched today. Monitoring only. {len(day_signals)} signals accumulated.","timestamp":n()}]})
            print(f"  Already launched today — monitoring only")
        else:
            post({"type":"identity","identity":{"mood":"hunting","status":f"accumulating (scan #{scan_count}/3+)"}})
            post({"type":"thoughts","thoughts":[{"type":"reflection","content":f"Scan #{scan_count} done. Need at least 3 scans before launching. Accumulating signals.","timestamp":n()}]})
            print(f"  Need at least 3 scans before considering launch ({scan_count} so far)")

        # Wait for next scan
        next_scan = datetime.datetime.utcnow() + datetime.timedelta(seconds=SCAN_INTERVAL)
        print(f"  Next scan at {next_scan.strftime('%H:%M UTC')} ({SCAN_INTERVAL//60} min)")
        post({"type":"identity","identity":{"status":f"next scan {next_scan.strftime('%H:%M UTC')}"}})

        time.sleep(SCAN_INTERVAL)

    except KeyboardInterrupt:
        print("\niSpawn stopped by user.")
        post({"type":"identity","identity":{"mood":"idle","status":"stopped"}})
        log('daemon_stop', 'Stopped by user', 0, 'system', 'ispawn')
        break
    except Exception as ex:
        print(f"  ERROR: {ex}")
        log('error', str(ex)[:300], 1, 'system', 'ispawn')
        time.sleep(60)

ssh.close()
