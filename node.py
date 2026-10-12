"""
Flask REST API and networked node for the MyCoin cryptocurrency.
Provides endpoints for transactions, blocks, mining, peer registration,
and longest-valid-chain consensus resolution.
"""

import argparse
import json
import os
import sys
import threading
from typing import Any
from flask import Flask, current_app, jsonify, request
import requests

from config import (
    COIN_NAME,
    DATA_DIR,
    DEFAULT_PORT,
    DIFFICULTY,
    MINING_REWARD,
    REQUEST_TIMEOUT_SECONDS,
    SYMBOL,
    SYNC_INTERVAL_SECONDS,
)
from wallet import Wallet
from blockchain import Blockchain, Block, Transaction


def normalize_url(url: str) -> str:
    """
    Normalize peer URL: strip whitespace and trailing slashes.
    Must start with http:// or https://.
    """
    if not isinstance(url, str):
        raise ValueError("URL must be a string")
    normalized = url.strip().rstrip("/")
    if not (normalized.startswith("http://") or normalized.startswith("https://")):
        raise ValueError("URL must start with http:// or https://")
    return normalized


class NodeState:
    """
    State container attached to a Flask app instance.
    Holds the blockchain, peer URL set, threading lock, wallet, and persistence settings.
    No module-level global state is used, enabling independent test instances.
    """

    def __init__(
        self,
        port: int,
        public_url: str,
        data_dir: str,
        wallet: Wallet,
        blockchain: Blockchain,
        data_file_path: str,
    ) -> None:
        self.port: int = port
        self.public_url: str = public_url
        self.data_dir: str = data_dir
        self.wallet: Wallet = wallet
        self.blockchain: Blockchain = blockchain
        self.data_file_path: str = data_file_path
        self.peers: set[str] = set()
        self.lock: threading.Lock = threading.Lock()
        self.stop_event: threading.Event = threading.Event()


def save_chain_to_disk(node_state: NodeState) -> None:
    """Save the current blockchain to a local JSON file."""
    os.makedirs(node_state.data_dir, exist_ok=True)
    with open(node_state.data_file_path, "w", encoding="utf-8") as f:
        json.dump(node_state.blockchain.to_dict(), f, indent=2)


def broadcast_post(peers: list[str], endpoint: str, data: dict[str, Any]) -> None:
    """
    Broadcast a JSON payload to a list of peers concurrently in background daemon threads.
    Fire-and-forget; never blocks the caller or crashes on peer failure.
    """
    def send_task(peer_url: str) -> None:
        try:
            target_url = f"{peer_url}{endpoint}"
            requests.post(target_url, json=data, timeout=REQUEST_TIMEOUT_SECONDS)
        except Exception as e:
            # Short warning log without crashing the node
            print(f"Broadcast to {peer_url}{endpoint} failed: {e}")

    for peer in peers:
        thread = threading.Thread(target=send_task, args=(peer,), daemon=True)
        thread.start()


def resolve_consensus(node_state: NodeState) -> bool:
    """
    Query all known peers for their chains and replace our chain if a strictly
    longer valid chain is found.
    Thread safety: Network requests are executed OUTSIDE the lock.
    """
    with node_state.lock:
        peers_to_query = list(node_state.peers)

    replaced_any = False

    for peer in peers_to_query:
        try:
            # Query peer's chain without holding the lock
            resp = requests.get(f"{peer}/chain", timeout=REQUEST_TIMEOUT_SECONDS)
            if resp.status_code != 200:
                continue
            chain_payload = resp.json()
            if not isinstance(chain_payload, dict) or "chain" not in chain_payload:
                continue

            candidate_chain = Blockchain.from_dict(chain_payload["chain"])

            # Acquire lock to check and replace chain
            with node_state.lock:
                if node_state.blockchain.replace_chain_if_longer(candidate_chain.chain):
                    save_chain_to_disk(node_state)
                    replaced_any = True
        except Exception as e:
            # Handle peer error independently and continue
            print(f"Consensus sync with {peer} failed: {e}")
            continue

    return replaced_any


def background_sync_worker(node_state: NodeState) -> None:
    """Periodically execute consensus sync across all peers in the background."""
    while not node_state.stop_event.is_set():
        node_state.stop_event.wait(SYNC_INTERVAL_SECONDS)
        if node_state.stop_event.is_set():
            break
        with node_state.lock:
            has_peers = len(node_state.peers) > 0
        if has_peers:
            resolve_consensus(node_state)


def create_app(
    port: int = DEFAULT_PORT,
    public_url: str | None = None,
    data_dir: str = DATA_DIR,
    start_background: bool = True,
) -> Flask:
    """
    Application factory for a MyCoin node.
    Initializes wallet, loaded or fresh blockchain, state container, and API routes.
    """
    app = Flask(__name__)
    normalized_public_url = normalize_url(public_url or f"http://127.0.0.1:{port}")

    # Load or generate the node's wallet
    wallet_dir = "wallets"
    os.makedirs(wallet_dir, exist_ok=True)
    wallet_path = os.path.join(wallet_dir, f"node_{port}.json")
    if os.path.exists(wallet_path):
        try:
            wallet = Wallet.load_from_file(wallet_path)
        except Exception as e:
            print(f"Warning: Failed to load wallet at {wallet_path}: {e}. Generating new wallet.")
            wallet = Wallet()
            wallet.save_to_file(wallet_path)
    else:
        wallet = Wallet()
        wallet.save_to_file(wallet_path)

    # Chain persistence initialization
    os.makedirs(data_dir, exist_ok=True)
    data_file_path = os.path.join(data_dir, f"chain_{port}.json")
    blockchain = Blockchain()

    if os.path.exists(data_file_path):
        try:
            with open(data_file_path, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
            loaded_bc = Blockchain.from_dict(saved_data)
            valid, reason = Blockchain.is_valid_chain(loaded_bc.chain)
            if valid:
                blockchain = loaded_bc
            else:
                print(f"WARNING: Persisted chain at {data_file_path} invalid ({reason}). Starting fresh chain.")
        except Exception as e:
            print(f"WARNING: Could not load persisted chain from {data_file_path}: {e}. Starting fresh chain.")

    node_state = NodeState(
        port=port,
        public_url=normalized_public_url,
        data_dir=data_dir,
        wallet=wallet,
        blockchain=blockchain,
        data_file_path=data_file_path,
    )
    app.node_state = node_state  # type: ignore
    app.config["NODE_STATE"] = node_state

    # Start periodic consensus polling if requested
    if start_background:
        t = threading.Thread(target=background_sync_worker, args=(node_state,), daemon=True)
        t.start()

    # -------------------------------------------------------------
    # Helper for adding & broadcasting transactions
    # -------------------------------------------------------------
    def _process_transaction(tx: Transaction) -> tuple[dict[str, Any], int]:
        with node_state.lock:
            tx_id = tx.tx_id()
            # Check duplicate in mempool or confirmed chain
            if any(p.tx_id() == tx_id for p in node_state.blockchain.pending_transactions) or \
               any(t.tx_id() == tx_id for b in node_state.blockchain.chain for t in b.transactions):
                return {"ok": True, "message": "already known", "tx_id": tx_id}, 200

            accepted, reason = node_state.blockchain.add_transaction(tx)
            if not accepted:
                return {"ok": False, "message": reason}, 400

            peers_to_notify = list(node_state.peers)

        # Broadcast outside the lock to avoid blocking
        broadcast_post(peers_to_notify, "/transactions/new", tx.to_dict())
        return {"ok": True, "message": "Transaction accepted", "tx_id": tx.tx_id()}, 201

    # -------------------------------------------------------------
    # Endpoints
    # -------------------------------------------------------------
    @app.route("/", methods=["GET"])
    def node_info():
        with node_state.lock:
            info = {
                "coin_name": COIN_NAME,
                "symbol": SYMBOL,
                "address": node_state.wallet.address,
                "public_url": node_state.public_url,
                "chain_length": len(node_state.blockchain.chain),
                "pending_count": len(node_state.blockchain.pending_transactions),
                "peer_count": len(node_state.peers),
                "difficulty": DIFFICULTY,
            }
        return jsonify(info), 200

    @app.route("/wallet/new", methods=["GET"])
    def new_wallet():
        w = Wallet()
        return jsonify({
            "address": w.address,
            "private_key": w.private_key_hex,
            "warning": "Demo only - never share or expose private keys in production",
        }), 200

    @app.route("/chain", methods=["GET"])
    def get_chain():
        with node_state.lock:
            data = {
                "length": len(node_state.blockchain.chain),
                "chain": [b.to_dict() for b in node_state.blockchain.chain],
            }
        return jsonify(data), 200

    @app.route("/pending", methods=["GET"])
    def get_pending():
        with node_state.lock:
            pending = [tx.to_dict() for tx in node_state.blockchain.pending_transactions]
        return jsonify(pending), 200

    @app.route("/balance/<address>", methods=["GET"])
    def get_balance(address: str):
        with node_state.lock:
            bal = node_state.blockchain.get_balance(address)
        return jsonify({"address": address, "balance": bal}), 200

    @app.route("/transactions/new", methods=["POST"])
    def post_transaction():
        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict):
            return jsonify({"ok": False, "message": "Invalid JSON body"}), 400

        try:
            tx = Transaction.from_dict(data)
        except Exception as e:
            return jsonify({"ok": False, "message": f"Malformed transaction: {e}"}), 400

        resp_data, status_code = _process_transaction(tx)
        return jsonify(resp_data), status_code

    @app.route("/demo/send", methods=["POST"])
    def demo_send():
        """
        Demo endpoint: signs and submits a transaction on behalf of the given private key.
        WARNING: Transmitting private keys over a network is strictly for demo purposes!
        """
        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict):
            return jsonify({"ok": False, "message": "Invalid JSON body"}), 400

        priv_key = data.get("private_key")
        receiver = data.get("receiver")
        amount = data.get("amount")
        tx_data = data.get("data", "")

        if not priv_key or not receiver or amount is None:
            return jsonify({
                "ok": False,
                "message": "Missing required fields: private_key, receiver, and amount",
            }), 400

        try:
            sender_wallet = Wallet.from_private_key_hex(priv_key)
        except Exception as e:
            return jsonify({"ok": False, "message": f"Invalid private key: {e}"}), 400

        tx = Transaction(
            sender=sender_wallet.address,
            receiver=receiver,
            amount=amount,
            data=tx_data,
        )
        tx.sign_with(sender_wallet)

        resp_data, status_code = _process_transaction(tx)
        return jsonify(resp_data), status_code

    @app.route("/mine", methods=["GET"])
    def mine_block():
        miner_addr = request.args.get("miner")
        if not miner_addr:
            miner_addr = node_state.wallet.address

        with node_state.lock:
            # Educational simplification: mining holds the lock because difficulty=3 completes in milliseconds
            block = node_state.blockchain.mine_pending_transactions(miner_addr)
            save_chain_to_disk(node_state)
            new_balance = node_state.blockchain.get_balance(miner_addr)
            peers_to_notify = list(node_state.peers)

        # Broadcast newly mined block to all peers outside the lock
        broadcast_post(peers_to_notify, "/blocks/receive", block.to_dict())

        return jsonify({
            "ok": True,
            "block": block.to_dict(),
            "balance": new_balance,
            "miner": miner_addr,
        }), 200

    @app.route("/blocks/receive", methods=["POST"])
    def receive_block():
        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict):
            return jsonify({"ok": False, "message": "Invalid JSON body"}), 400

        try:
            block = Block.from_dict(data)
        except Exception as e:
            return jsonify({"ok": False, "message": f"Malformed block: {e}"}), 400

        peers_to_notify: list[str] = []
        broadcast_block: dict[str, Any] | None = None
        needs_resolve: bool = False

        with node_state.lock:
            last_block = node_state.blockchain.chain[-1]

            # 1. Block already in our chain (same hash at index) or older
            if block.index <= last_block.index:
                if node_state.blockchain.chain[block.index].hash == block.hash:
                    return jsonify({"ok": True, "message": "already known"}), 200
                # Different block at same or earlier height indicates a fork
                needs_resolve = True

            # 2. Block is immediate next sequential block linking to current tip
            elif block.index == last_block.index + 1 and block.previous_hash == last_block.hash:
                accepted, reason = node_state.blockchain.add_block(block)
                if not accepted:
                    return jsonify({"ok": False, "message": reason}), 400
                save_chain_to_disk(node_state)
                peers_to_notify = list(node_state.peers)
                broadcast_block = block.to_dict()

            # 3. Block is further ahead or does not link to tip (out of sync / fork)
            else:
                needs_resolve = True

        if broadcast_block:
            broadcast_post(peers_to_notify, "/blocks/receive", broadcast_block)
            return jsonify({"ok": True, "message": "Block accepted", "block": broadcast_block}), 201

        if needs_resolve:
            replaced = resolve_consensus(node_state)
            return jsonify({
                "ok": True,
                "message": "out of sync, resolve executed",
                "replaced": replaced,
            }), 200

        return jsonify({"ok": False, "message": "Unhandled block condition"}), 400

    @app.route("/nodes/register", methods=["POST"])
    def register_nodes():
        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict) or "nodes" not in data:
            return jsonify({"ok": False, "message": "Expected JSON body with 'nodes' list"}), 400

        raw_nodes = data.get("nodes")
        if not isinstance(raw_nodes, list):
            return jsonify({"ok": False, "message": "'nodes' must be a list of URLs"}), 400

        reciprocal = data.get("reciprocal", True)

        normalized_nodes = []
        for url in raw_nodes:
            if not isinstance(url, str):
                return jsonify({"ok": False, "message": "Node URLs must be strings"}), 400
            try:
                norm = normalize_url(url)
                normalized_nodes.append(norm)
            except ValueError as e:
                return jsonify({"ok": False, "message": str(e)}), 400

        newly_added = []
        with node_state.lock:
            for norm in normalized_nodes:
                if norm == node_state.public_url:
                    continue
                if norm not in node_state.peers:
                    node_state.peers.add(norm)
                    newly_added.append(norm)
            all_peers = sorted(list(node_state.peers))

        # Perform reciprocal registration for newly added peers
        if reciprocal and newly_added:
            for new_peer in newly_added:
                def send_reciprocal(target: str) -> None:
                    try:
                        requests.post(
                            f"{target}/nodes/register",
                            json={"nodes": [node_state.public_url], "reciprocal": False},
                            timeout=REQUEST_TIMEOUT_SECONDS,
                        )
                    except Exception as e:
                        print(f"Reciprocal registration with {target} failed: {e}")

                threading.Thread(target=send_reciprocal, args=(new_peer,), daemon=True).start()

        # Trigger one consensus sync after adding peers
        if newly_added:
            threading.Thread(target=resolve_consensus, args=(node_state,), daemon=True).start()

        return jsonify(all_peers), 200

    @app.route("/nodes", methods=["GET"])
    def get_nodes():
        with node_state.lock:
            all_peers = sorted(list(node_state.peers))
        return jsonify(all_peers), 200

    @app.route("/nodes/resolve", methods=["GET"])
    def resolve_nodes():
        replaced = resolve_consensus(node_state)
        with node_state.lock:
            length = len(node_state.blockchain.chain)
        return jsonify({"replaced": replaced, "length": length}), 200

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"{COIN_NAME} Networked Blockchain Node")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to run node on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface to bind")
    parser.add_argument("--public-url", type=str, default=None, help="Public URL of this node")
    parser.add_argument("--peers", nargs="*", default=[], help="Initial peer URLs to register with")
    args = parser.parse_args()

    node_port = args.port
    node_public_url = args.public_url or f"http://127.0.0.1:{node_port}"

    app_instance = create_app(
        port=node_port,
        public_url=node_public_url,
        start_background=True,
    )
    state = app_instance.node_state  # type: ignore

    # Register CLI peers on startup
    if args.peers:
        for p in args.peers:
            try:
                norm_peer = normalize_url(p)
                if norm_peer != state.public_url:
                    state.peers.add(norm_peer)
                    def send_startup_reciprocal(peer_target: str) -> None:
                        try:
                            requests.post(
                                f"{peer_target}/nodes/register",
                                json={"nodes": [state.public_url], "reciprocal": False},
                                timeout=REQUEST_TIMEOUT_SECONDS,
                            )
                        except Exception as e:
                            print(f"Startup reciprocal registration with {peer_target} failed: {e}")
                    threading.Thread(target=send_startup_reciprocal, args=(norm_peer,), daemon=True).start()
            except ValueError as val_err:
                print(f"Skipping invalid startup peer {p}: {val_err}")

    # Run resolve once on startup
    resolve_consensus(state)

    print("=" * 60)
    print(f"  {COIN_NAME} Node Online")
    print(f"  Public URL:   {state.public_url}")
    print(f"  Node Address: {state.wallet.address}")
    print(f"  Chain Length: {len(state.blockchain.chain)}")
    print(f"  Peers ({len(state.peers)}): {sorted(list(state.peers))}")
    print("=" * 60)

    app_instance.run(
        host=args.host,
        port=node_port,
        threaded=True,
        debug=False,
        use_reloader=False,
    )
