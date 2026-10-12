"""
Test suite for MyCoin networked node: Flask REST API, peer management,
block broadcasting, consensus resolution, and Blockchain.add_block.
"""

import json
import os
import sys
import pytest
import requests

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import COIN_NAME, DIFFICULTY, MINING_REWARD, SYMBOL
from wallet import Wallet
from blockchain import Blockchain, Block, Transaction
from node import create_app


@pytest.fixture
def app_and_client(tmp_path, monkeypatch):
    """
    Fixture providing a test Flask app and client with isolated data directory
    and mocked outbound requests.
    """
    # Prevent real network calls during tests
    def dummy_post(url, *args, **kwargs):
        class DummyResponse:
            status_code = 200
            def json(self):
                return {"ok": True}
        return DummyResponse()

    monkeypatch.setattr(requests, "post", dummy_post)

    app = create_app(
        port=5000,
        public_url="http://127.0.0.1:5000",
        data_dir=str(tmp_path),
        start_background=False,
    )
    client = app.test_client()
    return app, client


# =====================================================================
# 1. Blockchain.add_block Unit Tests
# =====================================================================

def test_add_block_valid_accepted():
    """Verify that a valid next block is accepted by Blockchain.add_block."""
    bc = Blockchain()
    miner = Wallet()
    helper_bc = Blockchain()

    block1 = helper_bc.mine_pending_transactions(miner.address)
    ok, reason = bc.add_block(block1)
    assert ok is True
    assert reason == "ok"
    assert len(bc.chain) == 2
    assert bc.chain[-1].hash == block1.hash
    assert bc.get_balance(miner.address) == MINING_REWARD


def test_add_block_wrong_previous_hash_rejected():
    """Verify that a block with mismatched previous_hash is rejected."""
    bc = Blockchain()
    miner = Wallet()
    helper_bc = Blockchain()

    block1 = helper_bc.mine_pending_transactions(miner.address)
    block1.previous_hash = "deadbeef" * 8

    ok, reason = bc.add_block(block1)
    assert ok is False
    assert "previous_hash" in reason
    assert len(bc.chain) == 1


def test_add_block_tampered_block_rejected():
    """Verify that a tampered block (corrupted reward) fails add_block."""
    bc = Blockchain()
    miner = Wallet()
    helper_bc = Blockchain()

    block1 = helper_bc.mine_pending_transactions(miner.address)
    block1.transactions[0].amount = 9999
    block1.hash = block1.compute_hash()

    ok, reason = bc.add_block(block1)
    assert ok is False
    assert "Invalid block" in reason
    assert len(bc.chain) == 1


def test_add_block_wrong_index_rejected():
    """Verify that a block with non-sequential index is rejected."""
    bc = Blockchain()
    miner = Wallet()
    helper_bc = Blockchain()

    block1 = helper_bc.mine_pending_transactions(miner.address)
    block1.index = 99

    ok, reason = bc.add_block(block1)
    assert ok is False
    assert "Invalid block index" in reason


# =====================================================================
# 2. Node API Endpoint Tests
# =====================================================================

def test_get_node_info(app_and_client):
    """Verify that GET / returns the node's configuration and status."""
    _, client = app_and_client
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["coin_name"] == COIN_NAME
    assert data["symbol"] == SYMBOL
    assert data["chain_length"] == 1
    assert data["pending_count"] == 0
    assert data["peer_count"] == 0
    assert data["difficulty"] == DIFFICULTY
    assert "address" in data
    assert "public_url" in data


def test_wallet_new_endpoint(app_and_client):
    """Verify that GET /wallet/new generates a valid wallet key pair."""
    _, client = app_and_client
    resp = client.get("/wallet/new")
    assert resp.status_code == 200
    data = resp.get_json()

    assert "address" in data
    assert "private_key" in data
    assert "warning" in data

    # Verify that the returned private key matches the address
    rebuilt = Wallet.from_private_key_hex(data["private_key"])
    assert rebuilt.address == data["address"]


def test_mine_with_miner_param(app_and_client):
    """Verify that GET /mine?miner=<address> rewards the specified address."""
    _, client = app_and_client
    custom_miner = Wallet()

    resp = client.get(f"/mine?miner={custom_miner.address}")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["ok"] is True
    assert data["balance"] == MINING_REWARD
    assert data["miner"] == custom_miner.address

    # Check /balance/<address>
    bal_resp = client.get(f"/balance/{custom_miner.address}")
    assert bal_resp.status_code == 200
    assert bal_resp.get_json()["balance"] == MINING_REWARD


def test_demo_send_and_mining(app_and_client):
    """Verify that /demo/send queues a transaction and mining confirms it."""
    _, client = app_and_client
    alice = Wallet()
    bob = Wallet()

    # Credit Alice by mining
    client.get(f"/mine?miner={alice.address}")

    # Alice sends 20 to Bob using /demo/send
    send_resp = client.post(
        "/demo/send",
        json={
            "private_key": alice.private_key_hex,
            "receiver": bob.address,
            "amount": 20,
            "data": "Demo coffee",
        },
    )
    assert send_resp.status_code == 201
    assert send_resp.get_json()["ok"] is True

    # Check transaction appears in /pending
    pending_resp = client.get("/pending")
    assert pending_resp.status_code == 200
    pending_list = pending_resp.get_json()
    assert len(pending_list) == 1
    assert pending_list[0]["sender"] == alice.address
    assert pending_list[0]["receiver"] == bob.address
    assert pending_list[0]["amount"] == 20

    # Mine block to confirm transaction
    client.get("/mine")

    # Pending pool is now empty
    assert len(client.get("/pending").get_json()) == 0

    # Balances reflect confirmed transfer
    alice_bal = client.get(f"/balance/{alice.address}").get_json()["balance"]
    bob_bal = client.get(f"/balance/{bob.address}").get_json()["balance"]
    assert alice_bal == 30  # 50 - 20
    assert bob_bal == 20


def test_insufficient_balance_returns_400(app_and_client):
    """Verify that /demo/send rejects spending more coins than available."""
    _, client = app_and_client
    alice = Wallet()
    bob = Wallet()

    # Alice has 0 balance
    resp = client.post(
        "/demo/send",
        json={
            "private_key": alice.private_key_hex,
            "receiver": bob.address,
            "amount": 10,
        },
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "Insufficient balance" in data["message"]


def test_forged_signature_returns_400(app_and_client):
    """Verify that /transactions/new rejects a transaction with a forged signature."""
    _, client = app_and_client
    alice = Wallet()
    bob = Wallet()

    client.get(f"/mine?miner={alice.address}")

    # Transaction from Alice, forged signature by Bob
    tx = Transaction(sender=alice.address, receiver=bob.address, amount=10)
    tx.sign_with(bob)

    resp = client.post("/transactions/new", json=tx.to_dict())
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "Invalid transaction signature" in data["message"]


def test_duplicate_transaction_returns_200_already_known(app_and_client):
    """Verify that submitting an already known transaction returns 200 without error."""
    _, client = app_and_client
    alice = Wallet()
    bob = Wallet()

    client.get(f"/mine?miner={alice.address}")

    tx = Transaction(sender=alice.address, receiver=bob.address, amount=10, timestamp=500.0)
    tx.sign_with(alice)

    # First submission accepted
    resp1 = client.post("/transactions/new", json=tx.to_dict())
    assert resp1.status_code == 201

    # Second submission returns 200 "already known"
    resp2 = client.post("/transactions/new", json=tx.to_dict())
    assert resp2.status_code == 200
    data = resp2.get_json()
    assert data["ok"] is True
    assert "already known" in data["message"]


def test_invalid_amount_returns_400(app_and_client):
    """Verify that zero or negative transaction amounts return 400."""
    _, client = app_and_client
    alice = Wallet()
    bob = Wallet()
    client.get(f"/mine?miner={alice.address}")

    resp_neg = client.post(
        "/demo/send",
        json={
            "private_key": alice.private_key_hex,
            "receiver": bob.address,
            "amount": -5,
        },
    )
    assert resp_neg.status_code == 400

    resp_zero = client.post(
        "/demo/send",
        json={
            "private_key": alice.private_key_hex,
            "receiver": bob.address,
            "amount": 0,
        },
    )
    assert resp_zero.status_code == 400


def test_blocks_receive_endpoint(app_and_client):
    """
    Verify /blocks/receive:
    - accepts valid sequential block (201)
    - returns 200 for duplicate block
    - rejects tampered block (400)
    """
    _, client = app_and_client
    miner = Wallet()
    helper_bc = Blockchain()

    block1 = helper_bc.mine_pending_transactions(miner.address)

    # Valid block accepted
    resp1 = client.post("/blocks/receive", json=block1.to_dict())
    assert resp1.status_code == 201
    assert resp1.get_json()["ok"] is True

    # Same block again returns 200 "already known"
    resp_dup = client.post("/blocks/receive", json=block1.to_dict())
    assert resp_dup.status_code == 200
    assert resp_dup.get_json()["message"] == "already known"

    # Mine block 2 on helper, then tamper with its hash
    block2 = helper_bc.mine_pending_transactions(miner.address)
    tampered_dict = block2.to_dict()
    tampered_dict["hash"] = "0" * 64

    resp_tampered = client.post("/blocks/receive", json=tampered_dict)
    assert resp_tampered.status_code == 400
    assert resp_tampered.get_json()["ok"] is False


def test_nodes_register_endpoint(app_and_client):
    """Verify /nodes/register adds valid peers, ignores self, and rejects invalid URLs."""
    app, client = app_and_client

    # Bad URL returns 400
    resp_bad = client.post(
        "/nodes/register",
        json={"nodes": ["invalid-url"], "reciprocal": False},
    )
    assert resp_bad.status_code == 400
    assert resp_bad.get_json()["ok"] is False

    # Valid registration, including self-reference which must be ignored
    resp_ok = client.post(
        "/nodes/register",
        json={
            "nodes": [
                "http://127.0.0.1:5001/",
                "http://127.0.0.1:5002",
                app.node_state.public_url,  # self URL
            ],
            "reciprocal": False,
        },
    )
    assert resp_ok.status_code == 200
    peers = resp_ok.get_json()
    assert "http://127.0.0.1:5001" in peers
    assert "http://127.0.0.1:5002" in peers
    assert app.node_state.public_url not in peers

    # GET /nodes returns same peers
    resp_get = client.get("/nodes")
    assert resp_get.status_code == 200
    assert resp_get.get_json() == peers


def test_nodes_resolve_consensus(tmp_path, monkeypatch):
    """
    Verify /nodes/resolve:
    - Adopts a longer valid chain from a peer
    - Rejects a longer invalid chain from a peer
    """
    app = create_app(
        port=5000,
        public_url="http://127.0.0.1:5000",
        data_dir=str(tmp_path),
        start_background=False,
    )
    client = app.test_client()

    # Add a mock peer
    app.node_state.peers.add("http://peer1:5001")

    # Case A: Peer has longer valid chain
    longer_valid = Blockchain()
    longer_valid.mine_pending_transactions("miner1")
    longer_valid.mine_pending_transactions("miner1")  # Length 3

    class MockRespValid:
        status_code = 200
        def json(self):
            return longer_valid.to_dict()

    monkeypatch.setattr(requests, "get", lambda url, *args, **kwargs: MockRespValid())

    resp = client.get("/nodes/resolve")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["replaced"] is True
    assert data["length"] == 3
    assert len(app.node_state.blockchain.chain) == 3

    # Case B: Peer has longer INVALID chain (e.g. length 4 with illegal reward)
    longer_invalid = Blockchain()
    longer_invalid.mine_pending_transactions("miner1")
    longer_invalid.mine_pending_transactions("miner1")
    longer_invalid.mine_pending_transactions("miner1")  # Length 4
    longer_invalid.chain[2].transactions[0].amount = 999999
    longer_invalid.chain[2].hash = longer_invalid.chain[2].compute_hash()

    class MockRespInvalid:
        status_code = 200
        def json(self):
            return longer_invalid.to_dict()

    monkeypatch.setattr(requests, "get", lambda url, *args, **kwargs: MockRespInvalid())

    resp_inv = client.get("/nodes/resolve")
    assert resp_inv.status_code == 200
    data_inv = resp_inv.get_json()
    assert data_inv["replaced"] is False
    assert data_inv["length"] == 3  # Unchanged length
    assert len(app.node_state.blockchain.chain) == 3


def test_persistence_roundtrip(tmp_path):
    """Verify that mined blocks are saved to disk and restored across app restarts."""
    port = 5050
    data_dir = str(tmp_path)

    # Instance 1: mine two blocks
    app1 = create_app(port=port, public_url=f"http://127.0.0.1:{port}", data_dir=data_dir, start_background=False)
    client1 = app1.test_client()
    client1.get("/mine")
    client1.get("/mine")
    assert len(app1.node_state.blockchain.chain) == 3

    # Instance 2: reload from same data directory
    app2 = create_app(port=port, public_url=f"http://127.0.0.1:{port}", data_dir=data_dir, start_background=False)
    client2 = app2.test_client()
    chain_resp = client2.get("/chain")
    assert chain_resp.status_code == 200
    assert chain_resp.get_json()["length"] == 3
    assert len(app2.node_state.blockchain.chain) == 3
