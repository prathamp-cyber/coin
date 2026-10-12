"""
Step-by-step educational demo for MyCoin Core Blockchain.
Demonstrates wallets, mining, transactions, validation, balance tracking,
and cryptographic tamper detection.
"""

from config import COIN_NAME, DIFFICULTY, MINING_REWARD, SYMBOL
from blockchain import Blockchain, Transaction
from wallet import Wallet


def format_address(addr: str) -> str:
    """Format a long hex address for readable console display."""
    if len(addr) > 20:
        return f"{addr[:8]}...{addr[-8:]}"
    return addr


def main() -> None:
    print("=" * 60)
    print(f"       WELCOME TO THE {COIN_NAME.upper()} ({SYMBOL}) BLOCKCHAIN DEMO")
    print(f"       Proof of Work Difficulty: {DIFFICULTY} leading zeros")
    print(f"       Mining Reward: {MINING_REWARD} {SYMBOL} per block")
    print("=" * 60)
    print()

    # ---------------------------------------------------------
    # Step 1: Create wallets for Alice, Bob, and Miner
    # ---------------------------------------------------------
    print("--- [Step 1] Creating Wallets for Alice, Bob, and Miner ---")
    alice = Wallet()
    bob = Wallet()
    miner = Wallet()

    print(f"Alice's Address: {format_address(alice.address)}")
    print(f"Bob's Address:   {format_address(bob.address)}")
    print(f"Miner's Address: {format_address(miner.address)}")
    print()

    # Initialize a new blockchain
    bc = Blockchain()
    print(f"Initialized new blockchain with Genesis Block (Index 0, Hash: {bc.chain[0].hash[:16]}...)")
    print()

    # ---------------------------------------------------------
    # Step 2: Alice mines a block to earn coins; print balances
    # ---------------------------------------------------------
    print("--- [Step 2] Alice Mines a Block to Earn Coins ---")
    print("Alice is mining block #1...")
    block_1 = bc.mine_pending_transactions(alice.address)
    print(f"Block #1 mined! Nonce: {block_1.nonce}, Hash: {block_1.hash}")
    print("Balances after Block #1:")
    print(f"  Alice: {bc.get_balance(alice.address)} {SYMBOL}")
    print(f"  Bob:   {bc.get_balance(bob.address)} {SYMBOL}")
    print(f"  Miner: {bc.get_balance(miner.address)} {SYMBOL}")
    print()

    # ---------------------------------------------------------
    # Step 3: Alice sends 20 to Bob (signed transaction); show it is pending
    # ---------------------------------------------------------
    print("--- [Step 3] Alice Sends 20 MYC to Bob (Signed Transaction) ---")
    tx1 = Transaction(
        sender=alice.address,
        receiver=bob.address,
        amount=20,
        data="Payment for coffee",
    )
    tx1.sign_with(alice)
    print(f"Transaction created: {format_address(tx1.sender)} -> {format_address(tx1.receiver)}, Amount: {tx1.amount} {SYMBOL}")
    print(f"Signature verified: {tx1.is_valid_signature()}")

    accepted, reason = bc.add_transaction(tx1)
    print(f"Added to mempool: {accepted} (Reason: {reason})")
    print(f"Current mempool pending transactions count: {len(bc.pending_transactions)}")
    print(f"Mempool transaction tx_id: {bc.pending_transactions[0].tx_id()[:16]}...")
    print("Notice: Balances do not change until the transaction is mined into a block!")
    print(f"  Alice confirmed balance: {bc.get_balance(alice.address)} {SYMBOL}")
    print(f"  Bob confirmed balance:   {bc.get_balance(bob.address)} {SYMBOL}")
    print()

    # ---------------------------------------------------------
    # Step 4: Miner mines the block; print all balances
    # ---------------------------------------------------------
    print("--- [Step 4] Miner Mines the Block ---")
    print("Miner is mining block #2 containing Alice's payment and Miner's reward...")
    block_2 = bc.mine_pending_transactions(miner.address)
    print(f"Block #2 mined! Nonce: {block_2.nonce}, Hash: {block_2.hash}")
    print(f"Transactions in Block #2: {len(block_2.transactions)}")
    print(f"Pending transactions remaining in mempool: {len(bc.pending_transactions)}")
    print("Balances after Block #2:")
    print(f"  Alice: {bc.get_balance(alice.address)} {SYMBOL} (50 earned - 20 sent = 30)")
    print(f"  Bob:   {bc.get_balance(bob.address)} {SYMBOL} (20 received)")
    print(f"  Miner: {bc.get_balance(miner.address)} {SYMBOL} (50 mining reward)")
    print()

    # ---------------------------------------------------------
    # Step 5: Try to send more than the balance; show the rejection reason
    # ---------------------------------------------------------
    print("--- [Step 5] Alice Tries to Send More Than Her Balance ---")
    print(f"Alice's current balance is {bc.get_balance(alice.address)} {SYMBOL}.")
    print(f"Alice attempts to send 100 {SYMBOL} to Bob...")
    excess_tx = Transaction(
        sender=alice.address,
        receiver=bob.address,
        amount=100,
    )
    excess_tx.sign_with(alice)
    accepted, reason = bc.add_transaction(excess_tx)
    print(f"Transaction Accepted: {accepted}")
    print(f"Rejection Reason:    {reason}")
    print()

    # ---------------------------------------------------------
    # Step 6: Try a transaction with a forged signature; show the rejection reason
    # ---------------------------------------------------------
    print("--- [Step 6] Transaction with a Forged Signature ---")
    print("Attacker Bob creates a transaction from Alice's address, but signs it with Bob's key...")
    forged_tx = Transaction(
        sender=alice.address,
        receiver=bob.address,
        amount=15,
    )
    forged_tx.sign_with(bob)  # Bob fraudulently signs as Alice!
    accepted, reason = bc.add_transaction(forged_tx)
    print(f"Transaction Accepted: {accepted}")
    print(f"Rejection Reason:    {reason}")
    print()

    # ---------------------------------------------------------
    # Step 7: Tamper with an old transaction; run is_valid_chain
    # ---------------------------------------------------------
    print("--- [Step 7] Tampering with an Old Transaction in the Blockchain ---")
    valid_before, status_before = Blockchain.is_valid_chain(bc.chain)
    print(f"Current chain validation status: valid={valid_before} ({status_before})")

    print("\n[Tamper Event] Malicious actor alters Block #2, Transaction #1 (Alice -> Bob):")
    original_amount = bc.chain[2].transactions[1].amount
    print(f"  Modifying amount from {original_amount} {SYMBOL} to 9999 {SYMBOL}...")
    bc.chain[2].transactions[1].amount = 9999

    valid_after, status_after = Blockchain.is_valid_chain(bc.chain)
    print(f"Chain validation status after tampering: valid={valid_after}")
    print(f"Validation Failure Reason: {status_after}")
    print()
    print("=" * 60)
    print("DEMO COMPLETE: All cryptographic and consensus rules verified!")
    print("=" * 60)


if __name__ == "__main__":
    main()
