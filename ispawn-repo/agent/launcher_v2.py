import requests, json, time, sys, base64, subprocess, os
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction
from solders.message import Message
from solders.hash import Hash

PRIVATE_KEY = os.environ.get("SOLANA_PRIVATE_KEY", "")
RPC = "https://rpc.solanatracker.io/public"

def launch_token(name, symbol, description, dev_buy_sol=0.0):
    signer = Keypair.from_base58_string(PRIVATE_KEY)
    print(f"Wallet: {signer.pubkey()}")

    # 1. Create Lightning wallet
    print("Creating PumpPortal Lightning wallet...")
    wr = requests.get("https://pumpportal.fun/api/create-wallet", timeout=15)
    wd = wr.json()
    api_key = wd['apiKey']
    lightning_pub = wd['walletPublicKey']
    print(f"Lightning wallet: {lightning_pub}")

    # 2. Transfer SOL to Lightning wallet
    # pump.fun create_v2 needs ~0.02 SOL for rent (mint, bonding curve, ATA, etc.) + jito tip + priority fee
    transfer_amount = max(int((dev_buy_sol + 0.022) * 1e9), 22_000_000)
    print(f"Transferring {transfer_amount/1e9} SOL...")

    bh_resp = requests.post(RPC, json={"jsonrpc":"2.0","id":1,"method":"getLatestBlockhash","params":[{"commitment":"confirmed"}]}, timeout=10)
    blockhash = bh_resp.json()['result']['value']['blockhash']

    ix = transfer(TransferParams(
        from_pubkey=signer.pubkey(),
        to_pubkey=Pubkey.from_string(lightning_pub),
        lamports=transfer_amount
    ))
    msg = Message.new_with_blockhash([ix], signer.pubkey(), Hash.from_string(blockhash))
    tx = Transaction.new_unsigned(msg)
    tx.sign([signer], Hash.from_string(blockhash))

    tx_b64 = base64.b64encode(bytes(tx)).decode('utf-8')
    send_resp = requests.post(RPC, json={
        "jsonrpc":"2.0","id":1,"method":"sendTransaction",
        "params":[tx_b64, {"encoding":"base64","skipPreflight":False,"preflightCommitment":"confirmed"}]
    }, timeout=15)
    send_json = send_resp.json()

    if 'error' in send_json:
        result = {"success": False, "error": f"SOL transfer failed: {send_json['error']}"}
        print(f"RESULT_JSON:{json.dumps(result)}")
        return result

    print(f"Transfer TX: {send_json['result']}")
    print("Waiting for confirmation...")
    time.sleep(8)

    # 3. Generate image
    print("Generating token image...")
    subprocess.run(['python3', '/opt/agent-factory/gen_image.py', symbol, name], check=True, capture_output=True)
    subprocess.run(['mkdir', '-p', '/opt/agent-factory/public/tokens/'], capture_output=True)

    # 4. Upload to IPFS
    print("Uploading to IPFS...")
    form_data = {
        'name': name,
        'symbol': symbol,
        'description': description,
        'website': 'https://ispawn.fun',
        'twitter': 'https://x.com/ispawn_fun',
        'showName': 'true'
    }
    with open('/tmp/token_image.png', 'rb') as f:
        file_content = f.read()
    files = {'file': ('token.png', file_content, 'image/png')}
    mr = requests.post("https://pump.fun/api/ipfs", data=form_data, files=files, timeout=30)

    if mr.status_code != 200:
        result = {"success": False, "error": f"IPFS upload failed: {mr.status_code}"}
        print(f"RESULT_JSON:{json.dumps(result)}")
        return result

    uri = mr.json()['metadataUri']
    print(f"IPFS URI: {uri}")

    # 5. Launch via Lightning API
    print("Launching on pump.fun...")
    mint_keypair = Keypair()
    print(f"Token mint: {mint_keypair.pubkey()}")

    resp = requests.post(
        f"https://pumpportal.fun/api/trade?api-key={api_key}",
        headers={'Content-Type': 'application/json'},
        data=json.dumps({
            'action': 'create',
            'tokenMetadata': {'name': name, 'symbol': symbol, 'uri': uri},
            'mint': str(mint_keypair),
            'denominatedInSol': 'true',
            'amount': dev_buy_sol,
            'slippage': 10,
            'priorityFee': 0.0005,
            'pool': 'pump'
        }),
        timeout=30
    )

    if resp.status_code == 200:
        data = resp.json()
        if 'signature' in data:
            mint = str(mint_keypair.pubkey())
            sig = data['signature']

            # Verify transaction succeeded on-chain
            print(f"Verifying TX on-chain...")
            time.sleep(5)
            tx_verified = False
            for attempt in range(3):
                try:
                    tx_resp = requests.post(RPC, json={
                        "jsonrpc":"2.0","id":1,"method":"getTransaction",
                        "params":[sig, {"encoding":"json","commitment":"confirmed","maxSupportedTransactionVersion":0}]
                    }, timeout=15)
                    tx_data = tx_resp.json()
                    if tx_data.get('result'):
                        meta = tx_data['result'].get('meta', {})
                        err = meta.get('err')
                        if err:
                            result = {"success": False, "error": f"TX failed on-chain: {err}. Token mint created but bonding curve failed. Need more SOL for rent."}
                            print(f"RESULT_JSON:{json.dumps(result)}")
                            return result
                        tx_verified = True
                        print(f"TX confirmed on-chain (no errors)")
                        break
                    else:
                        print(f"TX not found yet, retrying... ({attempt+1}/3)")
                        time.sleep(5)
                except Exception as e:
                    print(f"Verification error: {e}, retrying...")
                    time.sleep(3)

            if not tx_verified:
                print("WARNING: Could not verify TX, proceeding anyway")

            print(f"\n=== TOKEN LAUNCHED ===")
            print(f"Mint: {mint}")
            print(f"TX: https://solscan.io/tx/{sig}")
            print(f"Pump: https://pump.fun/{mint}")
            # Fetch the image URL from IPFS metadata
            image_url = None
            try:
                meta_resp = requests.get(uri, timeout=10)
                if meta_resp.status_code == 200:
                    meta = meta_resp.json()
                    image_url = meta.get('image', None)
            except:
                pass

            # Save a local copy as fallback
            try:
                import shutil
                local_path = f"/opt/agent-factory/public/tokens/{mint}.png"
                shutil.copy2('/tmp/token_image.png', local_path)
                local_url = f"/tokens/{mint}.png"
                if not image_url:
                    image_url = local_url
            except:
                pass

            result = {
                "success": True, "mint": mint, "tx": sig, "name": name, "symbol": symbol,
                "pump_url": f"https://pump.fun/{mint}",
                "solscan_url": f"https://solscan.io/tx/{sig}",
                "metadata_uri": uri,
                "image_url": image_url,
                "local_image": f"/tokens/{mint}.png",
                "description": description,
                "website": "https://ispawn.fun"
            }
            print(f"RESULT_JSON:{json.dumps(result)}")
            return result
        else:
            result = {"success": False, "error": f"Launch errors: {data.get('errors', str(data)[:200])}"}
            print(f"RESULT_JSON:{json.dumps(result)}")
            return result
    else:
        result = {"success": False, "error": f"PumpPortal {resp.status_code}: {resp.text[:200]}"}
        print(f"RESULT_JSON:{json.dumps(result)}")
        return result

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 launcher_v2.py <name> <symbol> <description> [dev_buy_sol]")
        sys.exit(1)
    name = sys.argv[1]
    symbol = sys.argv[2]
    desc = sys.argv[3]
    dev_buy = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    launch_token(name, symbol, desc, dev_buy)
