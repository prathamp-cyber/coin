"""
Comprehensive test suite for MyCoin core blockchain logic.
Covers cryptographic signatures, transaction verification, mempool rules,
mining, consensus validation, chain replacement, and serialization.
"""

import os
import sys
import tempfile
import pytest

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import (
    DIFFICULTY,
    GENESIS_TIMESTAMP,
    MINING_REWARD,
    SYSTEM_ADDRESS,
)
from wallet import Wallet, verify_signature
from blockchain import Blockchain, Block, Transaction


# =====================================================================
# 1. Cryptographic Signatures and Wallet Tests
# =====================================================================

def test_valid_signature_accepted():
    """Verify that a properly signed payload is validated successfully."""
    wallet = Wallet()
    payload = b"Sample transaction payload"
    sig = wallet.sign(payload)
    assert verify_signature(wallet.address, payload, sig) is True


def test_wrong_signature_rejected():
    """Verify that a signature from a different key pair is rejected."""
    wallet_alice = Wallet()
    wallet_bob = Wallet()
    payload = b"Transfer 10 MYC"

    # Alice's address checked against Bob's signature
    bob_sig = wallet_bob.sign(payload)
    assert verify_signature(wallet_alice.address, payload, bob_sig) is False


def test_verify_signature_malformed_input_never_raises():
    """Verify that invalid hex, corrupted types, or bad lengths return False and never raise."""
    wallet = Wallet()
    payload = b"Valid payload"
    sig = wallet.sign(payload)

    # Corrupted / invalid hex strings
    assert verify_signature("not_hex", payload, sig) is False
    assert verify_signature(wallet.address, payload, "not_hex") is False
    assert verify_signature(wallet.address, payload, "123") is False  # Odd length hex
    assert verify_signature(wallet.address, "not_bytes", sig) is False  # type: ignore
    assert verify_signature(None, payload, sig) is False  # type: ignore
    assert verify_signature(wallet.address, payload, None) is False  # type: ignore
    assert verify_signature("", payload, sig) is False
    assert verify_signature(wallet.address, payload, "") is False


def test_modified_transaction_rejected():
    """Verify that altering any field in a signed transaction invalidates its signature."""
    alice = Wallet()
    bob = Wallet()
    tx = Transaction(sender=alice.address, receiver=bob.address, amount=10, data="Lunch")
    tx.sign_with(alice)
    assert tx.is_valid_signature() is True

    # Tamper with the amount
    tx.amount = 100
    assert tx.is_valid_signature() is False

    # Restore amount, tamper with data
    tx.amount = 10
    tx.data = "Dinner"
    assert tx.is_valid_signature() is False

    # Restore data, tamper with receiver
    tx.data = "Lunch"
    tx.receiver = alice.address
    assert tx.is_valid_signature() is False


def test_wallet_save_and_load_roundtrip():
    """Verify that saving a wallet to disk and loading it preserves the private key and address."""
    wallet = Wallet()
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "test_wallet.json")
        wallet.save_to_file(filepath)
        assert os.path.exists(filepath)

        loaded_wallet = Wallet.load_from_file(filepath)
        assert loaded_wallet.address == wallet.address
        assert loaded_wallet.get_private_key_hex() == wallet.get_private_key_hex()

        # Loaded wallet signs and verifies identically
        payload = b"Test message"
        sig = loaded_wallet.sign(payload)
        assert verify_signature(wallet.address, payload, sig) is True


# =====================================================================
# 2. Transaction Validation and Mempool Rules
# =====================================================================

def test_insufficient_balance_rejected():
    """Verify that accounts cannot spend more coins than their confirmed balance."""
    bc = Blockchain()
    alice = Wallet()
    bob = Wallet()

    # Alice has 0 confirmed balance
    tx = Transaction(sender=alice.address, receiver=bob.address, amount=10)
    tx.sign_with(alice)
    accepted, reason = bc.add_transaction(tx)
    assert accepted is False
    assert "Insufficient balance" in reason

    # Alice mines a block to receive MINING_REWARD (50)
    bc.mine_pending_transactions(alice.address)
    assert bc.get_balance(alice.address) == MINING_REWARD

    # Alice tries to send 60 (exceeding 50)
    tx_over = Transaction(sender=alice.address, receiver=bob.address, amount=60)
    tx_over.sign_with(alice)
    accepted, reason = bc.add_transaction(tx_over)
    assert accepted is False
    assert "Insufficient balance" in reason


def test_pending_outgoing_balance_deduction():
    """Verify that multiple pending outgoing transactions cannot exceed available balance."""
    bc = Blockchain()
    alice = Wallet()
    bob = Wallet()
    bc.mine_pending_transactions(alice.address)  # Alice has 50

    # First tx: 30 coins (remaining available: 20)
    tx1 = Transaction(sender=alice.address, receiver=bob.address, amount=30, timestamp=100.0)
    tx1.sign_with(alice)
    accepted1, _ = bc.add_transaction(tx1)
    assert accepted1 is True

    # Second tx: 25 coins (only 20 available) -> should be rejected
    tx2 = Transaction(sender=alice.address, receiver=bob.address, amount=25, timestamp=101.0)
    tx2.sign_with(alice)
    accepted2, reason = bc.add_transaction(tx2)
    assert accepted2 is False
    assert "Insufficient balance" in reason


def test_duplicate_transaction_rejected():
    """Verify that duplicate transactions (identical tx_id) cannot be submitted to mempool or chain."""
    bc = Blockchain()
    alice = Wallet()
    bob = Wallet()
    bc.mine_pending_transactions(alice.address)

    tx = Transaction(sender=alice.address, receiver=bob.address, amount=10, timestamp=100.0)
    tx.sign_with(alice)

    # First submission accepted
    accepted1, _ = bc.add_transaction(tx)
    assert accepted1 is True

    # Duplicate in mempool rejected
    accepted2, reason2 = bc.add_transaction(tx)
    assert accepted2 is False
    assert "already pending" in reason2

    # Mine block containing tx
    bc.mine_pending_transactions(alice.address)

    # Re-submitting mined transaction rejected
    accepted3, reason3 = bc.add_transaction(tx)
    assert accepted3 is False
    assert "already exists in chain" in reason3


def test_invalid_transaction_rules():
    """Verify rejection of zero/negative amounts, sender equals receiver, and SYSTEM sender."""
    bc = Blockchain()
    alice = Wallet()
    bob = Wallet()
    bc.mine_pending_transactions(alice.address)

    # Negative amount
    tx_neg = Transaction(sender=alice.address, receiver=bob.address, amount=-5)
    tx_neg.sign_with(alice)
    ok, reason = bc.add_transaction(tx_neg)
    assert ok is False
    assert "positive integer" in reason

    # Zero amount
    tx_zero = Transaction(sender=alice.address, receiver=bob.address, amount=0)
    tx_zero.sign_with(alice)
    ok, reason = bc.add_transaction(tx_zero)
    assert ok is False
    assert "positive integer" in reason

    # Sender equals receiver
    tx_self = Transaction(sender=alice.address, receiver=alice.address, amount=5)
    tx_self.sign_with(alice)
    ok, reason = bc.add_transaction(tx_self)
    assert ok is False
    assert "Sender cannot be receiver" in reason

    # Sender is SYSTEM_ADDRESS
    tx_sys = Transaction(sender=SYSTEM_ADDRESS, receiver=bob.address, amount=10)
    ok, reason = bc.add_transaction(tx_sys)
    assert ok is False
    assert "SYSTEM" in reason


# =====================================================================
# 3. Mining, Difficulty, and Genesis Block Tests
# =====================================================================

def test_mining_reward_credited_to_miner():
    """Verify that mining a block creates and credits the reward transaction to the miner."""
    bc = Blockchain()
    miner = Wallet()
    assert bc.get_balance(miner.address) == 0

    block = bc.mine_pending_transactions(miner.address)
    assert len(block.transactions) == 1
    assert block.transactions[0].sender == SYSTEM_ADDRESS
    assert block.transactions[0].receiver == miner.address
    assert block.transactions[0].amount == MINING_REWARD
    assert bc.get_balance(miner.address) == MINING_REWARD


def test_block_hash_meets_difficulty():
    """Verify that mined block hashes meet the target difficulty constraint."""
    bc = Blockchain()
    miner = Wallet()
    block = bc.mine_pending_transactions(miner.address)
    target = "0" * DIFFICULTY
    assert block.hash.startswith(target)
    assert block.hash == block.compute_hash()


def test_two_separate_instances_have_identical_genesis_blocks():
    """Verify that any two Blockchain instances create an identical, deterministic genesis block."""
    bc1 = Blockchain()
    bc2 = Blockchain()
    gen1 = bc1.chain[0]
    gen2 = bc2.chain[0]

    assert gen1.index == 0
    assert gen1.timestamp == GENESIS_TIMESTAMP
    assert gen1.previous_hash == "0"
    assert gen1.nonce == 0
    assert gen1.transactions == []
    assert gen1.hash == gen2.hash
    assert gen1.to_dict() == gen2.to_dict()


# =====================================================================
# 4. Chain Validation and Tamper Detection Tests
# =====================================================================

def test_tampered_block_makes_chain_invalid():
    """Verify that modifying a transaction in a mined block fails validation."""
    bc = Blockchain()
    alice = Wallet()
    bob = Wallet()

    bc.mine_pending_transactions(alice.address)
    tx = Transaction(sender=alice.address, receiver=bob.address, amount=15)
    tx.sign_with(alice)
    bc.add_transaction(tx)
    bc.mine_pending_transactions(alice.address)

    # Valid chain initially
    is_valid, reason = Blockchain.is_valid_chain(bc.chain)
    assert is_valid is True
    assert reason == "ok"

    # Tamper with the transaction amount in block #2
    bc.chain[2].transactions[1].amount = 500
    is_valid_tampered, reason_tampered = Blockchain.is_valid_chain(bc.chain)
    assert is_valid_tampered is False
    assert ("Stored hash does not match" in reason_tampered or "Invalid" in reason_tampered)


def test_broken_previous_hash_link_makes_chain_invalid():
    """Verify that corrupting the previous_hash link between blocks invalidates the chain."""
    bc = Blockchain()
    miner = Wallet()
    bc.mine_pending_transactions(miner.address)
    bc.mine_pending_transactions(miner.address)

    # Tamper with the linkage
    bc.chain[2].previous_hash = "deadbeef" * 8
    # Even if we recompute the hash for block 2, the linkage to block 1 is broken
    bc.chain[2].hash = bc.chain[2].compute_hash()

    is_valid, reason = Blockchain.is_valid_chain(bc.chain)
    assert is_valid is False
    assert "Broken previous_hash link" in reason


def test_invalid_genesis_block_rejected():
    """Verify that a chain with an altered genesis block is rejected."""
    bc = Blockchain()
    bc.chain[0].nonce = 999
    bc.chain[0].hash = bc.chain[0].compute_hash()

    is_valid, reason = Blockchain.is_valid_chain(bc.chain)
    assert is_valid is False
    assert "Invalid genesis block" in reason


# =====================================================================
# 5. Consensus: Chain Replacement Tests
# =====================================================================

def test_longer_valid_chain_replaces_shorter_one():
    """Verify that a strictly longer valid chain replaces a shorter chain."""
    node_a = Blockchain()
    node_b = Blockchain()
    miner_a = Wallet()
    miner_b = Wallet()

    node_a.mine_pending_transactions(miner_a.address)  # node_a has 2 blocks (genesis + 1)
    node_b.mine_pending_transactions(miner_b.address)  # node_b has 2 blocks
    node_b.mine_pending_transactions(miner_b.address)  # node_b has 3 blocks

    assert len(node_b.chain) > len(node_a.chain)
    replaced = node_a.replace_chain_if_longer(node_b.chain)
    assert replaced is True
    assert len(node_a.chain) == 3
    assert node_a.chain == node_b.chain


def test_longer_invalid_chain_is_not_accepted():
    """Verify that a longer chain containing invalid Proof of Work or data is rejected."""
    node_a = Blockchain()
    node_b = Blockchain()
    miner = Wallet()

    node_a.mine_pending_transactions(miner.address)  # length 2
    node_b.mine_pending_transactions(miner.address)
    node_b.mine_pending_transactions(miner.address)  # length 3

    # Invalidate block 2 of node_b (tamper with reward amount)
    node_b.chain[2].transactions[0].amount = 9999
    node_b.chain[2].hash = node_b.chain[2].compute_hash()

    replaced = node_a.replace_chain_if_longer(node_b.chain)
    assert replaced is False
    assert len(node_a.chain) == 2


def test_same_length_or_shorter_chain_not_replaced():
    """Verify that chains of equal or shorter length do not replace current chain."""
    node_a = Blockchain()
    node_b = Blockchain()
    miner = Wallet()

    node_a.mine_pending_transactions(miner.address)
    node_b.mine_pending_transactions(miner.address)

    # Same length: 2 blocks
    assert node_a.replace_chain_if_longer(node_b.chain) is False


# =====================================================================
# 6. Serialization Tests
# =====================================================================

def test_from_dict_to_dict_roundtrip_produces_identical_chain():
    """Verify that serializing to dict and rebuilding the chain preserves exact state."""
    bc = Blockchain()
    alice = Wallet()
    bob = Wallet()

    bc.mine_pending_transactions(alice.address)
    tx = Transaction(sender=alice.address, receiver=bob.address, amount=20, data="Roundtrip test")
    tx.sign_with(alice)
    bc.add_transaction(tx)
    bc.mine_pending_transactions(bob.address)

    # Serialize
    chain_dict = bc.to_dict()
    assert isinstance(chain_dict, dict)
    assert "chain" in chain_dict

    # Reconstruct
    rebuilt_bc = Blockchain.from_dict(chain_dict)
    assert bc == rebuilt_bc
    assert len(rebuilt_bc.chain) == len(bc.chain)

    for b1, b2 in zip(bc.chain, rebuilt_bc.chain):
        assert b1.to_dict() == b2.to_dict()
        assert b1.hash == b2.hash
        assert b1.compute_hash() == b2.compute_hash()

    # Rebuilt chain passes is_valid_chain
    is_valid, reason = Blockchain.is_valid_chain(rebuilt_bc.chain)
    assert is_valid is True
    assert reason == "ok"
