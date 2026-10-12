# MyCoin (Phase 1: Core & Networked Node)

An educational cryptocurrency blockchain implementation written in Python.

- **Phase 1, Part 1 (Core)**: SECP256k1 elliptic curve signatures, deterministic genesis block, Proof of Work mining puzzle, balance calculation, mempool rules, and consensus validation.
- **Phase 1, Part 2 (Networked Node)**: Flask REST API, peer registration, block & transaction broadcasting, longest-valid-chain consensus resolution, and disk persistence.

---

## Installation

Ensure Python 3.10 or newer is installed:

```bash
pip install -r requirements.txt
```

---

## Running the Core Demo

Run the standalone 7-step cryptographic and consensus demo (no server required):

```bash
python demo_core.py
```

---

## Running Tests

Run the full test suite with `pytest`:

```bash
pytest -v
```

This validates both the core blockchain logic (`tests/test_core.py`) and node networking / endpoints (`tests/test_node.py`).

---

## Running a Networked Node

Run a node via command line:

```bash
python node.py --port 5000 --host 0.0.0.0 --public-url http://127.0.0.1:5000
```

Available CLI arguments:
- `--port`: Local port to bind (default: `5000`).
- `--host`: Host interface to bind (default: `0.0.0.0`).
- `--public-url`: Publicly reachable URL for this node (default: `http://127.0.0.1:<port>`).
- `--peers`: Space-separated list of initial peer URLs to connect with.

---

## API Endpoints

All endpoints produce JSON. Error responses return `{"ok": false, "message": "..."}` with an appropriate HTTP status code.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Node information (coin name, symbol, address, public URL, chain length, pending count, peer count, difficulty). |
| `GET` | `/wallet/new` | Generates a new key pair (`address`, `private_key`, demo warning). |
| `GET` | `/chain` | Returns full blockchain (`length`, `chain` block dicts). |
| `GET` | `/pending` | Returns list of pending mempool transactions. |
| `GET` | `/balance/<address>` | Returns confirmed balance for the given address. |
| `POST` | `/transactions/new` | Submits a pre-signed transaction (`sender`, `receiver`, `amount`, `data`, `timestamp`, `signature`). Broadcasts to peers if newly accepted. |
| `POST` | `/demo/send` | Signs and submits a transaction given `{private_key, receiver, amount, data}` (strictly for demo/testing). |
| `GET` | `/mine` | Mines pending transactions. Optional `?miner=<address>` (defaults to node wallet). Broadcasts block to peers. |
| `POST` | `/blocks/receive` | Receives an incoming block from a peer. Appends if sequential (201), ignores if known (200), or triggers consensus resolve if out of sync. |
| `POST` | `/nodes/register` | Registers peer nodes given `{"nodes": ["http://..."], "reciprocal": true}`. Performs reciprocal handshake and syncs chain. |
| `GET` | `/nodes` | Returns list of connected peer URLs. |
| `GET` | `/nodes/resolve` | Manually triggers consensus resolution across all peers (`replaced`, `length`). |

---

## cURL Examples

### 1. Create a New Wallet
```bash
curl http://127.0.0.1:5000/wallet/new
```

### 2. Mine Coins to Earn Rewards
Mine to the node's default wallet:
```bash
curl http://127.0.0.1:5000/mine
```
Or mine directly to a specific address:
```bash
curl "http://127.0.0.1:5000/mine?miner=<YOUR_ADDRESS>"
```

### 3. Send Coins with `/demo/send`
```bash
curl -X POST http://127.0.0.1:5000/demo/send \
  -H "Content-Type: application/json" \
  -d '{
    "private_key": "<SENDER_PRIVATE_KEY_HEX>",
    "receiver": "<RECEIVER_PUBLIC_ADDRESS_HEX>",
    "amount": 25,
    "data": "Payment for services"
  }'
```

### 4. Check an Address Balance
```bash
curl http://127.0.0.1:5000/balance/<ADDRESS_HEX>
```

### 5. Check Pending Transactions (Mempool)
```bash
curl http://127.0.0.1:5000/pending
```

### 6. Inspect Blockchain
```bash
curl http://127.0.0.1:5000/chain
```

---

## Running a 3-Node Local Cluster

Open three separate terminal windows to run nodes on ports 5000, 5001, and 5002:

### Terminal 1 (Node 1 on port 5000):
```bash
python node.py --port 5000
```

### Terminal 2 (Node 2 on port 5001, connecting to Node 1):
```bash
python node.py --port 5001 --peers http://127.0.0.1:5000
```

### Terminal 3 (Node 3 on port 5002, connecting to Node 1 and Node 2):
```bash
python node.py --port 5002 --peers http://127.0.0.1:5000 http://127.0.0.1:5001
```

### Registering Peers Dynamically via REST API:
You can also connect running nodes dynamically at any time using `/nodes/register`:

```bash
# Connect Node 1 to Node 2 (reciprocal handshake connects both ways):
curl -X POST http://127.0.0.1:5000/nodes/register \
  -H "Content-Type: application/json" \
  -d '{"nodes": ["http://127.0.0.1:5001"]}'

# Connect Node 1 to Node 3:
curl -X POST http://127.0.0.1:5000/nodes/register \
  -H "Content-Type: application/json" \
  -d '{"nodes": ["http://127.0.0.1:5002"]}'
```

Once registered, transactions sent to any node are automatically broadcast to all peers, and newly mined blocks propagate throughout the network. If any node falls behind, the longest-valid-chain consensus rule automatically synchronizes its ledger.
