# MyCoin: Educational Cryptocurrency Blockchain

## 1. What This Project Is
**MyCoin** is an educational, minimalist cryptocurrency blockchain prototype written in pure Python. It is designed specifically for students, educators, and engineers to understand how blockchains work from first principles—without the noise of heavyweight frameworks, production databases, or complex networking libraries.

> **DISCLAIMER:** This project is strictly for learning and demonstration. It is not real money, has no financial value, and must never be used in production environments.

---

## 2. Features
- **Cryptographic Security**: SECP256k1 elliptic curve digital signatures and SHA-256 hashing using the standard `ecdsa` and `hashlib` libraries.
- **Proof of Work (PoW)**: Computational puzzle mechanism requiring blocks to meet a configurable leading-zero hash difficulty.
- **Deterministic Genesis**: Guaranteed identical genesis block across all independently initialized network nodes.
- **Mempool & Ledger Integrity**: Double-spending prevention, signature validation, positive balance enforcement, and transaction deduplication.
- **Decentralized Networking**: Flask-based REST API enabling peer registration, reciprocal discovery, and asynchronous broadcasting.
- **Longest-Valid-Chain Consensus**: Automatic fork resolution that replaces shorter or lagging branches with the longest cryptographically valid chain.
- **Interactive UI Dashboard**: Lightweight, projector-friendly web interface served directly from each node without build tools or external CDNs.
- **Supply Chain Extensibility**: Arbitrary payload support via the transaction `data` field.

---

## 3. Architecture

```text
       +-------------------------------------------------------------+
       |                        Web Dashboard                        |
       |                     (ui/dashboard.html)                     |
       +------------------------------+------------------------------+
                                      | HTTP REST API
                                      v
+-----------------------------+               +-----------------------------+
|        Node A (5000)        |   Broadcast   |        Node B (5001)        |
|  +-----------------------+  |<=============>|  +-----------------------+  |
|  |       Mempool         |  |   Blocks &    |  |       Mempool         |  |
|  +-----------------------+  |     Txs       |  +-----------------------+  |
|  |     PoW Miner         |  |               |  |     PoW Miner         |  |
|  +-----------------------+  |               |  +-----------------------+  |
|  |      Blockchain       |  |               |  |      Blockchain       |  |
|  | [Genesis]->[B1]->[B2] |  |               |  | [Genesis]->[B1]->[B2] |  |
|  +-----------------------+  |               |  +-----------------------+  |
|  |  wallets/ & data/     |  |               |  |  wallets/ & data/     |  |
+--+--------------------------+               +--+--------------------------+
                 ^                                     ^
                 |                 Broadcast           |
                 +====================================>|
                 |                                     |
                 v                                     v
       +-------------------------------------------------------------+
       |                        Node C (5002)                        |
       |  +-----------------------+   +---------------------------+  |
       |  |       Mempool         |   |         Blockchain        |  |
       |  +-----------------------+   |    [Genesis]->[B1]->[B2]  |  |
       |  |      PoW Miner        |   +---------------------------+  |
       |  +-----------------------+   |    wallets/ & data/       |  |
       +-------------------------------------------------------------+
```

---

## 4. How It Works in Short

1. **Transaction Signing**:
   A sender generates a key pair using ECDSA on the SECP256k1 curve. The public address is the hex representation of the public key. When sending coins, the sender signs a deterministic JSON payload `{sender, receiver, amount, data, timestamp}` using SHA-256 and their private key.

2. **Mempool Verification**:
   When a node receives a transaction, it verifies that the amount is positive, sender does not equal receiver, the digital signature is valid, and the sender possesses sufficient confirmed balance minus any unconfirmed outgoing transactions. Valid transactions enter the memory pool (`pending_transactions`).

3. **Mining and Proof of Work**:
   A miner constructs a candidate block containing:
   - A newly minted reward transaction (`SYSTEM -> miner`, amount = 50 MYC) as the first transaction.
   - All pending transactions from the mempool.
   - The SHA-256 hash of the previous block tip.
   The miner increments a numeric `nonce` until the block hash begins with `DIFFICULTY` zeros (default: `3`).

4. **Network Broadcasting**:
   Upon solving a block or accepting a new transaction, the node asynchronously broadcasts the object to all known peers in background daemon threads. Nodes acknowledge known objects without re-broadcasting, preventing infinite loops.

5. **Longest-Valid-Chain Consensus**:
   If a node encounters a block from a different branch or detects that a peer has a longer chain, it executes the resolve procedure. It downloads the peer's chain, validates that all blocks satisfy genesis rules, index continuity, previous hash links, Proof of Work difficulty, valid signatures, and non-negative balances. If the peer chain is valid and strictly longer, the node replaces its local chain and prunes now-confirmed transactions from its mempool.

---

## 5. Installation

Ensure Python 3.10 or newer is installed.

```bash
git clone https://github.com/prathamp-cyber/coin.git
cd coin
pip install -r requirements.txt
```

---

## 6. Running the Tests

Run the complete test suite (36 unit and integration tests) using `pytest`:

```bash
pytest -v
```

This tests core cryptography, transaction validation, mempool logic, block hashing, consensus replacement, Flask REST endpoints, and disk persistence.

---

## 7. Running the Automated 3-Node Demo

Run the automated integration demo:

```bash
python demo_cluster.py
```

### What It Checks:
1. Spawns 3 independent node processes on ports `5100`, `5101`, and `5102` in temporary directories.
2. **Peer Discovery**: Verifies all nodes register each other as peers.
3. **Wallet Creation**: Generates keys for Alice and Bob on Node A.
4. **Mining Reward**: Alice mines Block 1 on Node A and receives 50 MYC.
5. **Block Propagation**: Verifies Block 1 propagates to Node B and Node C, crediting Alice's balance across all nodes.
6. **Transaction Propagation**: Alice sends 20 MYC to Bob via Node B; verifies mempools on Node A, B, and C contain the pending payment.
7. **Block Confirmation**: Node C mines Block 2; verifies Alice (30 MYC), Bob (20 MYC), and Node C (50 MYC) are confirmed across all nodes.
8. **Tamper Detection**: Submits a modified transaction inside an old block; verifies Node A rejects it with HTTP 400.
9. **Balance Bounds**: Verifies an overspending transaction (Bob attempting to send 1000 MYC) is rejected with HTTP 400.
10. **Offline Catch-Up**: Kills Node C, mines 2 additional blocks on Node A, restarts Node C, and verifies Node C automatically synchronizes with the longest valid chain.
11. **Total Consistency**: Confirms identical chains and balances across all nodes before shutting down cleanly.

---

## 8. Running 3 Nodes Manually on One Computer

Open three terminal windows:

### Terminal 1 (Node A on Port 5000):
```bash
python node.py --port 5000 --data-dir data/node_5000 --wallet-dir wallets/node_5000
```

### Terminal 2 (Node B on Port 5001):
```bash
python node.py --port 5001 --data-dir data/node_5001 --wallet-dir wallets/node_5001 --peers http://127.0.0.1:5000
```

### Terminal 3 (Node C on Port 5002):
```bash
python node.py --port 5002 --data-dir data/node_5002 --wallet-dir wallets/node_5002 --peers http://127.0.0.1:5000 http://127.0.0.1:5001
```

Once started, any transaction or mined block will automatically synchronize across all three terminals.

---

## 9. Using the Dashboard

Each running node hosts an interactive web dashboard. Navigate to:

```text
http://127.0.0.1:5000/dashboard
```

### Dashboard Features:
- **Node Connection Bar**: Switch to any peer node URL on the network and click **Connect**.
- **Live Auto-Refresh**: Polls node state every 3 seconds with a visual timestamp and error indicator.
- **Node Overview**: Displays coin symbol, miner address (with copy button), chain length, mempool count, peer count, and PoW difficulty.
- **Action Toolbar**:
  - `Mine Block`: Triggers Proof of Work mining and distributes rewards.
  - `Sync with Peers`: Manually executes longest-valid-chain consensus resolution.
  - `New Wallet`: Generates a demo key pair directly from the node.
- **Balance Lookup**: Query the confirmed coin balance of any public address hex.
- **Blocks List (Newest First)**: Inspect block index, hash, nonce, and timestamp. Click any block to expand and inspect its transaction list.
- **Connected Peers & Mempool**: Live inspection of connected peer URLs and unmined transactions.

---

## 10. Office / LAN Setup (Multi-Computer Demo)

You can run nodes across different physical machines on the same local area network (Wi-Fi or Ethernet).

### Step 1: Find Local IP Address
- **Windows**:
  ```cmd
  ipconfig
  ```
  Look for `IPv4 Address` under your active Wi-Fi or Ethernet adapter (e.g., `192.168.1.50`).
- **macOS**:
  ```bash
  ipconfig getifaddr en0
  ```
- **Linux**:
  ```bash
  hostname -I
  ```

### Step 2: Configure Firewall Rules
Nodes must accept incoming TCP connections on their assigned port. Administrator privileges are required.

- **Windows (Command Prompt as Administrator)**:
  ```cmd
  netsh advfirewall firewall add rule name="MyCoin Node 5000" dir=in action=allow protocol=TCP localport=5000
  ```
- **Linux (Ubuntu / Debian using UFW)**:
  ```bash
  sudo ufw allow 5000/tcp
  ```
- **macOS**:
  If prompted by macOS Application Firewall when running `node.py`, click **Allow Incoming Connections**.

### Step 3: Start Node on Each Machine
Run the node binding to `0.0.0.0` so it accepts connections from external network interfaces, specifying the computer's LAN IP in `--public-url`:

- **Machine 1 (`192.168.1.50`)**:
  ```bash
  python node.py --host 0.0.0.0 --port 5000 --public-url http://192.168.1.50:5000
  ```

- **Machine 2 (`192.168.1.51`)**:
  ```bash
  python node.py --host 0.0.0.0 --port 5000 --public-url http://192.168.1.51:5000 --peers http://192.168.1.50:5000
  ```

### Step 4: Verify Connectivity
From Machine 2, verify it can reach Machine 1:
```bash
curl http://192.168.1.50:5000/
```
Or open `http://192.168.1.50:5000/dashboard` in your browser.

### Step 5: Dynamic Peer Registration
If a node was started without `--peers`, register it dynamically at any time:
```bash
curl -X POST http://192.168.1.50:5000/nodes/register \
  -H "Content-Type: application/json" \
  -d '{"nodes": ["http://192.168.1.51:5000"]}'
```
Due to reciprocal registration, Machine 1 and Machine 2 will automatically pair in both directions.

### LAN Troubleshooting Checklist:
- **Firewall Blocking**: Ensure the incoming port rule was created with admin rights.
- **Wi-Fi Client Isolation**: Some guest or office networks block devices from communicating with each other. If peers cannot connect, switch to a mobile hotspot or private router.
- **Wrong IP Address**: Confirm you used the LAN IP (`192.168.x.x` or `10.x.x.x`), not `127.0.0.1` or a public WAN IP.
- **Port In Use**: If port 5000 is occupied, pick 5001 or 5002 using `--port`.
- **Code Consistency**: Ensure all machines run the identical version of `node.py`, `blockchain.py`, and `config.py`.

---

## 11. Security Notes and Educational Limitations

This project is built for clarity and education. It deliberately makes simplifications that are unsuitable for real financial systems:

1. **Demo Endpoints Expose Private Keys**: The `/wallet/new` and `/demo/send` endpoints transmit private keys over HTTP. In production cryptocurrencies, private keys never leave local client storage.
2. **Unencrypted Wire Protocol**: Peer-to-peer traffic uses plaintext HTTP without TLS or node mutual authentication.
3. **No Sybil Protection**: Any peer URL can be registered. Real networks use proof-of-work/stake weighting and peer reputation scoring.
4. **Low Proof of Work Difficulty**: Difficulty is set to 3 leading zeros (`DIFFICULTY = 3`) so demo blocks mine in milliseconds. Real networks dynamically adjust difficulty to maintain multi-minute targets.
5. **Synchronous Mining Lock**: Mining holds the internal state lock for simplicity. Real nodes mine asynchronously in separate worker threads.
6. **Mempool Non-Persistence**: Pending transactions live strictly in memory; if a node crashes before mining, pending transactions are lost.

---

## 12. Future Extension: Supply Chain Tracking

Every transaction in MyCoin includes an optional string field: **`data`**.

In this cryptocurrency phase, `data` is used for simple payment memos (e.g., `"Payment for coffee"`). In the upcoming supply chain project, this field will be used to record immutable lifecycle tracking events:

```json
{
  "sender": "<MANUFACTURER_ADDRESS>",
  "receiver": "<DISTRIBUTOR_ADDRESS>",
  "amount": 1,
  "data": "{\"sku\": \"MED-BATCH-409\", \"status\": \"PRODUCED\", \"temp_c\": 4.2, \"loc\": \"Warehouse A\"}",
  "timestamp": 1728734900.0,
  "signature": "<ECDSA_SIGNATURE>"
}
```

Because transaction payloads are signed by the sender and sealed inside mined Proof of Work blocks, the `data` field provides tamper-proof, non-repudiable audit logs for physical assets.

---

## 13. Project Structure

```text
mycoin/
│
├── config.py             # Blockchain & network constants (difficulty, reward, ports)
├── wallet.py             # SECP256k1 key generation, signing, verification, and file I/O
├── blockchain.py         # Transaction, Block, and Blockchain consensus engine
├── node.py               # Flask REST API, peer broadcasting, consensus sync, and CLI
├── demo_core.py          # Standalone 7-step cryptographic and ledger demonstration
├── demo_cluster.py       # Automated 10-step end-to-end multi-node integration test
├── requirements.txt      # Minimal dependencies (ecdsa, pytest, flask, requests)
├── .gitignore            # Ignores wallets/, data/, cache, and virtual environments
├── README.md             # Complete technical documentation and setup guide
│
├── ui/
│   └── dashboard.html    # Single-file monitoring dashboard (vanilla HTML/CSS/JS)
│
└── tests/
    ├── test_core.py      # 19 unit tests for core blockchain and cryptography
    └── test_node.py      # 17 integration tests for Flask API and consensus sync
```
